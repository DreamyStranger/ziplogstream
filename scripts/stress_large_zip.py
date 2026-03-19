#!/usr/bin/env python3
"""
scripts.stress_large_zip
========================

Manual stress test for streaming a very large ZIP member with ``zip-logstream``.

Overview
--------
Generates a large ZIP archive containing one text member and streams it through
``zip_logstream.LineStreamer``, measuring:

- total lines streamed
- total decoded bytes
- elapsed time
- throughput in MiB/s
- peak Python memory (optional, via ``tracemalloc``)

Purpose
-------
This is a manual stress tool, not an automated test. It is useful for verifying:

- streaming remains stable on very large inputs (1 GiB+)
- memory usage stays bounded regardless of input size
- throughput is acceptable on the target machine

The archive is generated incrementally so generation itself never holds the
full uncompressed text in memory at once.

Output
------
Results are printed to stdout. Use ``--report-out PATH`` to also save the
report as a plain-text file with a timestamp header.

Examples
--------
Generate and stream a 1 GiB archive::

    python scripts/stress_large_zip.py

Stream an existing archive without regenerating it::

    python scripts/stress_large_zip.py --skip-generate --zip-path .benchmarks/large_logs_1g.zip

Stream a 2 GiB archive and save the report::

    python scripts/stress_large_zip.py --size-gib 2 --report-out results/stress.txt --track-memory
"""

from __future__ import annotations

import argparse
import time
import tracemalloc
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from zip_logstream import LineStreamer, LineStreamerConfig

MiB = 1024 * 1024
GiB = 1024 * MiB


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class StressResult:
    """
    Metrics collected from one stress run.

    Attributes:
        zip_path:              Path to the ZIP archive that was streamed.
        decoded_bytes:         Total decoded bytes yielded.
        line_count:            Total lines yielded.
        elapsed_seconds:       Wall-clock time for the streaming pass.
        throughput_mib_per_sec: Decoded bytes / elapsed time in MiB/s.
        peak_memory_bytes:     Peak Python memory measured by tracemalloc,
                               or ``None`` if tracking was disabled.
    """

    zip_path: Path
    decoded_bytes: int
    line_count: int
    elapsed_seconds: float
    throughput_mib_per_sec: float
    peak_memory_bytes: int | None


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_bytes(num_bytes: int) -> str:
    """Format a byte count as a human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < MiB:
        return f"{num_bytes / 1024:.2f} KiB"
    if num_bytes < GiB:
        return f"{num_bytes / MiB:.2f} MiB"
    return f"{num_bytes / GiB:.2f} GiB"


def render_stress_report(result: StressResult) -> str:
    """
    Render a ``StressResult`` as a formatted multi-line report string.

    The returned string does not include a trailing newline.
    """
    lines = [
        "",
        "Streaming complete",
        "------------------",
        f"ZIP path:         {result.zip_path}",
        f"Decoded bytes:    {format_bytes(result.decoded_bytes)}",
        f"Lines streamed:   {result.line_count:,}",
        f"Elapsed time:     {result.elapsed_seconds:.2f} s",
        f"Throughput:       {result.throughput_mib_per_sec:.2f} MiB/s",
    ]
    if result.peak_memory_bytes is not None:
        lines.append(f"Peak Python mem:  {format_bytes(result.peak_memory_bytes)}")
    return "\n".join(lines)


def render_report_file(result: StressResult, timestamp: str) -> str:
    """
    Render a file-ready stress report with a timestamped header.

    Args:
        result:     Stress run result to format.
        timestamp:  ISO-8601 UTC timestamp string for the header.
    """
    header = "\n".join([
        "zip-logstream Stress Test Results",
        "=" * 32,
        f"Run at: {timestamp}",
    ])
    return header + render_stress_report(result) + "\n"


# ---------------------------------------------------------------------------
# ZIP generation and streaming
# ---------------------------------------------------------------------------


def generate_large_zip(
    zip_path: Path,
    member_name: str,
    target_size_bytes: int,
    *,
    line_template: str,
    encoding: str = "utf-8",
) -> None:
    """
    Generate a ZIP archive containing one large text member.

    The member is written line-by-line so the generator never holds the
    full uncompressed payload in memory at once.

    Args:
        zip_path:          Destination ZIP path (parent dirs are created).
        member_name:       ZIP member path inside the archive.
        target_size_bytes: Approximate uncompressed size to write.
        line_template:     Repeated line used to fill the member.
        encoding:          Encoding for ``line_template``.

    Raises:
        ValueError: If ``line_template`` encodes to zero bytes.
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)

    encoded_line = line_template.encode(encoding)
    if not encoded_line:
        raise ValueError("line_template must not encode to empty bytes")

    line_size = len(encoded_line)
    written = 0

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        with zf.open(member_name, "w") as member:
            while written < target_size_bytes:
                remaining = target_size_bytes - written
                chunk = encoded_line if remaining >= line_size else encoded_line[:remaining]
                member.write(chunk)
                written += len(chunk)


def stream_large_zip(
    zip_path: Path,
    target: str,
    *,
    config: LineStreamerConfig,
    track_memory: bool,
) -> StressResult:
    """
    Stream the ZIP member and collect performance metrics.

    Args:
        zip_path:      Path to the ZIP archive.
        target:        Member selector string passed to ``LineStreamer``.
        config:        Streaming configuration.
        track_memory:  Whether to measure peak Python memory with tracemalloc.

    Returns:
        A ``StressResult`` with timing and throughput data.
    """
    if track_memory:
        tracemalloc.start()

    started = time.perf_counter()
    total_lines = 0
    total_decoded_bytes = 0

    for line in LineStreamer(zip_path, target, config=config).stream():
        total_lines += 1
        total_decoded_bytes += len(line.encode(config.encoding, errors=config.errors))

    elapsed = time.perf_counter() - started

    peak_memory_bytes: int | None = None
    if track_memory:
        _, peak_memory_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    throughput = (total_decoded_bytes / MiB) / elapsed if elapsed > 0 else 0.0

    return StressResult(
        zip_path=zip_path,
        decoded_bytes=total_decoded_bytes,
        line_count=total_lines,
        elapsed_seconds=elapsed,
        throughput_mib_per_sec=throughput,
        peak_memory_bytes=peak_memory_bytes,
    )


# ---------------------------------------------------------------------------
# CLI and entry point
# ---------------------------------------------------------------------------


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Generate and stress-test streaming of a very large ZIP member.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--zip-path",
        type=Path,
        default=Path(".benchmarks/large_logs_1g.zip"),
        metavar="PATH",
        help="ZIP file path to generate (or stream from, if --skip-generate is set).",
    )
    parser.add_argument(
        "--member-name",
        default="logs/app.log",
        metavar="NAME",
        help="ZIP member name to generate and stream.",
    )
    parser.add_argument(
        "--size-gib",
        type=float,
        default=1.0,
        metavar="N",
        help="Approximate uncompressed member size in GiB.",
    )
    parser.add_argument(
        "--line-template",
        default="INFO request completed status=200 latency_ms=12 path=/healthcheck\n",
        metavar="TEXT",
        help="Line template repeated to build the large member.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1 << 20,
        metavar="BYTES",
        help="LineStreamer chunk size in bytes.",
    )
    parser.add_argument(
        "--max-line-bytes",
        type=int,
        default=32 * (1 << 20),
        metavar="BYTES",
        help="Maximum buffered line size before a forced flush.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding for generation and streaming.",
    )
    parser.add_argument(
        "--errors",
        default="replace",
        help="Decode error handler passed to LineStreamerConfig.",
    )
    parser.add_argument(
        "--track-memory",
        action="store_true",
        help="Track peak Python memory with tracemalloc.",
    )
    parser.add_argument(
        "--skip-generate",
        action="store_true",
        help="Skip ZIP generation; stream the existing file at --zip-path instead.",
    )
    parser.add_argument(
        "--report-out",
        type=Path,
        metavar="PATH",
        help="Save the streaming results report as plain text to PATH.",
    )
    return parser


def main() -> int:
    """Entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    target_size_bytes = int(args.size_gib * GiB)

    config = LineStreamerConfig(
        chunk_size=args.chunk_size,
        encoding=args.encoding,
        errors=args.errors,
        max_line_bytes=args.max_line_bytes,
    )

    if not args.skip_generate:
        print("Generating large ZIP archive...")
        print("-------------------------------")
        print(f"Target ZIP path:   {args.zip_path}")
        print(f"Member name:       {args.member_name}")
        print(f"Target size:       {args.size_gib:.2f} GiB decoded")
        generate_large_zip(
            zip_path=args.zip_path,
            member_name=args.member_name,
            target_size_bytes=target_size_bytes,
            line_template=args.line_template,
            encoding=args.encoding,
        )
        print("Generation complete.")

    print()
    print("Streaming large ZIP archive...")
    print("------------------------------")

    result = stream_large_zip(
        zip_path=args.zip_path,
        target=Path(args.member_name).name,
        config=config,
        track_memory=args.track_memory,
    )

    # Print report to stdout.
    report = render_stress_report(result)
    print(report)

    # Optionally save report to file with a timestamp header.
    if args.report_out is not None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        file_text = render_report_file(result, timestamp)
        args.report_out.parent.mkdir(parents=True, exist_ok=True)
        args.report_out.write_text(file_text, encoding="utf-8")
        print(f"\nWrote report to: {args.report_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
