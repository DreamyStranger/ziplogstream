#!/usr/bin/env python3
"""
scripts.benchmark_streaming
===========================

Performance benchmark for ``zip_logstream.LineStreamer``.

Overview
--------
Benchmarks end-to-end streaming performance across a set of synthetic ZIP
archives generated on demand, covering the full pipeline:

    ZIP archive -> member resolution -> ZIP member open -> BufferedLineReader -> lines

What it measures
----------------
For each benchmark case, the script measures:

- wall-clock duration (mean, median, min, max across repeated runs)
- number of lines yielded
- total decoded bytes
- throughput in MiB/s (mean and median)
- lines per second (mean and median)
- optional peak Python memory via ``tracemalloc``

Output
------
Per-run progress is written to stdout. A summary table is printed at the end.
Use ``--table-out PATH`` to also save the summary table as a plain-text file
(with a timestamped config header). Use ``--json-out PATH`` to save the full
per-run data as JSON.

This script is not part of the automated test suite. Benchmark results are
machine-dependent and should be run on demand.

Examples
--------
Run all default benchmark cases::

    python scripts/benchmark_streaming.py

Run one case with five repeats and memory tracking::

    python scripts/benchmark_streaming.py --case many-short-lines --repeat 5 --track-memory

Save both table and JSON results::

    python scripts/benchmark_streaming.py --table-out results/table.txt --json-out results/data.json

Use a persistent workspace so ZIPs are not regenerated every run::

    python scripts/benchmark_streaming.py --workspace .benchmarks
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
import tracemalloc
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import IO, Callable, Iterable

from zip_logstream import LineStreamer, LineStreamerConfig

MiB = 1024 * 1024


# ---------------------------------------------------------------------------
# Benchmark case definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BenchmarkCase:
    """
    Definition of one benchmark scenario.

    Attributes:
        name:
            Stable identifier used in ``--case`` selection.

        description:
            Human-readable explanation of the scenario.

        member_name:
            ZIP member path to generate and stream.

        content_factory:
            Callable that returns the member text payload.
    """

    name: str
    description: str
    member_name: str
    content_factory: Callable[[], str]


def build_many_short_lines() -> str:
    """High line-count, short LF-terminated log lines (400 k lines)."""
    return "INFO request completed status=200 latency_ms=12 path=/healthcheck\n" * 400_000


def build_medium_lines() -> str:
    """Structured medium-width log lines with realistic field payloads (120 k lines)."""
    lines: list[str] = []
    for i in range(120_000):
        lines.append(
            f"2026-03-11T12:00:{i % 60:02d}Z "
            f"service=api level=INFO req_id={i:08d} "
            f"user_id={i % 10000:05d} method=GET path=/v1/resource/{i % 250} "
            f"status=200 latency_ms={(i % 47) + 3} region=us-east-1\n"
        )
    return "".join(lines)


def build_crlf_lines() -> str:
    """Windows-style CRLF-terminated lines to exercise CR stripping (300 k lines)."""
    return "INFO windows-style log line with CRLF ending\r\n" * 300_000


def build_single_huge_line() -> str:
    """One unterminated 24 MiB line to exercise the oversized-buffer flush path."""
    return "X" * (24 * MiB)


def build_large_final_partial_line() -> str:
    """Many normal lines followed by a large final unterminated tail."""
    head = "INFO normal line before final partial tail\n" * 150_000
    tail = "TAIL" * (2 * MiB // 4)
    return head + tail


def build_empty_lines_dense() -> str:
    """Frequent empty lines interspersed with content (180 k chunks)."""
    return "alpha\n\nbeta\n\n\ncharlie\n" * 180_000


DEFAULT_CASES: tuple[BenchmarkCase, ...] = (
    BenchmarkCase(
        name="many-short-lines",
        description="High line-count case with short LF-terminated log lines.",
        member_name="logs/app.log",
        content_factory=build_many_short_lines,
    ),
    BenchmarkCase(
        name="medium-lines",
        description="Structured medium-width log lines with realistic field payloads.",
        member_name="logs/app.log",
        content_factory=build_medium_lines,
    ),
    BenchmarkCase(
        name="crlf-lines",
        description="Windows-style CRLF line endings through the full pipeline.",
        member_name="logs/app.log",
        content_factory=build_crlf_lines,
    ),
    BenchmarkCase(
        name="single-huge-line",
        description="One oversized unterminated line to exercise forced flush behavior.",
        member_name="logs/app.log",
        content_factory=build_single_huge_line,
    ),
    BenchmarkCase(
        name="large-final-partial-line",
        description="Many normal lines followed by a large final partial line.",
        member_name="logs/app.log",
        content_factory=build_large_final_partial_line,
    ),
    BenchmarkCase(
        name="dense-empty-lines",
        description="Frequent empty lines mixed with normal lines.",
        member_name="logs/app.log",
        content_factory=build_empty_lines_dense,
    ),
)


# ---------------------------------------------------------------------------
# Metrics dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RunMetrics:
    """Metrics collected from one timed benchmark run."""

    case_name: str
    run_index: int
    duration_seconds: float
    line_count: int
    decoded_bytes: int
    throughput_mib_per_sec: float
    lines_per_sec: float
    peak_memory_bytes: int | None


@dataclass(frozen=True, slots=True)
class CaseSummary:
    """Aggregate metrics across repeated runs for one benchmark case."""

    case_name: str
    description: str
    repeats: int
    line_count: int
    decoded_bytes: int
    mean_duration_seconds: float
    median_duration_seconds: float
    min_duration_seconds: float
    max_duration_seconds: float
    mean_throughput_mib_per_sec: float
    median_throughput_mib_per_sec: float
    mean_lines_per_sec: float
    median_lines_per_sec: float
    peak_memory_bytes_max: int | None


# ---------------------------------------------------------------------------
# ZIP generation
# ---------------------------------------------------------------------------


def create_zip_payload(zip_path: Path, member_name: str, text: str, encoding: str) -> None:
    """
    Create a ZIP archive containing one text member.

    Args:
        zip_path:      Output ZIP path.
        member_name:   Member path inside the archive.
        text:          Text payload to encode and write.
        encoding:      Encoding used for the member bytes.
    """
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(member_name, text.encode(encoding))


# ---------------------------------------------------------------------------
# Benchmark execution
# ---------------------------------------------------------------------------


def run_single_benchmark(
    *,
    zip_path: Path,
    target: str,
    config: LineStreamerConfig,
    track_memory: bool,
    run_index: int,
    case_name: str,
) -> RunMetrics:
    """Run one timed benchmark iteration and return its metrics."""
    if track_memory:
        tracemalloc.start()

    started = time.perf_counter()
    line_count = 0
    decoded_bytes = 0

    for line in LineStreamer(zip_path, target, config=config).stream():
        line_count += 1
        decoded_bytes += len(line.encode(config.encoding, errors=config.errors))

    duration = time.perf_counter() - started

    peak_memory_bytes: int | None
    if track_memory:
        _, peak_memory_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    else:
        peak_memory_bytes = None

    throughput_mib_per_sec = (decoded_bytes / MiB) / duration if duration > 0 else math.inf
    lines_per_sec = line_count / duration if duration > 0 else math.inf

    return RunMetrics(
        case_name=case_name,
        run_index=run_index,
        duration_seconds=duration,
        line_count=line_count,
        decoded_bytes=decoded_bytes,
        throughput_mib_per_sec=throughput_mib_per_sec,
        lines_per_sec=lines_per_sec,
        peak_memory_bytes=peak_memory_bytes,
    )


def summarize_case(case: BenchmarkCase, runs: list[RunMetrics]) -> CaseSummary:
    """Aggregate repeated run metrics into a single summary for one case."""
    durations = [r.duration_seconds for r in runs]
    throughputs = [r.throughput_mib_per_sec for r in runs]
    line_rates = [r.lines_per_sec for r in runs]
    peak_values = [r.peak_memory_bytes for r in runs if r.peak_memory_bytes is not None]

    first = runs[0]
    return CaseSummary(
        case_name=case.name,
        description=case.description,
        repeats=len(runs),
        line_count=first.line_count,
        decoded_bytes=first.decoded_bytes,
        mean_duration_seconds=statistics.mean(durations),
        median_duration_seconds=statistics.median(durations),
        min_duration_seconds=min(durations),
        max_duration_seconds=max(durations),
        mean_throughput_mib_per_sec=statistics.mean(throughputs),
        median_throughput_mib_per_sec=statistics.median(throughputs),
        mean_lines_per_sec=statistics.mean(line_rates),
        median_lines_per_sec=statistics.median(line_rates),
        peak_memory_bytes_max=max(peak_values) if peak_values else None,
    )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_bytes(num_bytes: int | None) -> str:
    """Format a byte count as a human-readable string."""
    if num_bytes is None:
        return "-"
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < MiB:
        return f"{num_bytes / 1024:.1f} KiB"
    return f"{num_bytes / MiB:.2f} MiB"


def format_run_metrics(metrics: RunMetrics) -> str:
    """Format one run's metrics as a compact single-line string."""
    return (
        f"  run {metrics.run_index + 1:>2}: "
        f"{metrics.duration_seconds:8.4f} s | "
        f"{metrics.decoded_bytes / MiB:8.2f} MiB | "
        f"{metrics.line_count:>10,d} lines | "
        f"{metrics.throughput_mib_per_sec:8.2f} MiB/s | "
        f"{metrics.lines_per_sec:10,.0f} lines/s | "
        f"peak mem {format_bytes(metrics.peak_memory_bytes)}"
    )


# Table column widths — defined once so header and rows stay in sync.
_COL_CASE = 24
_COL_MIB = 10
_COL_LINES = 12
_COL_MEAN_S = 10
_COL_MED_S = 10
_COL_MEAN_MIB = 12
_COL_MED_MIB = 14
_COL_MEAN_LPS = 14
_COL_PEAK = 12
_TABLE_WIDTH = (
    _COL_CASE + 1 + _COL_MIB + 1 + _COL_LINES + 1 + _COL_MEAN_S + 1
    + _COL_MED_S + 1 + _COL_MEAN_MIB + 1 + _COL_MED_MIB + 1
    + _COL_MEAN_LPS + 1 + _COL_PEAK
)


def render_summary_table(summaries: Iterable[CaseSummary]) -> str:
    """
    Render the benchmark summary table as a multi-line string.

    Returns an empty string if there are no summaries.
    """
    rows = list(summaries)
    if not rows:
        return ""

    sep = "=" * _TABLE_WIDTH
    thin = "-" * _TABLE_WIDTH
    header = (
        f"{'case':<{_COL_CASE}} "
        f"{'MiB':>{_COL_MIB}} "
        f"{'lines':>{_COL_LINES}} "
        f"{'mean s':>{_COL_MEAN_S}} "
        f"{'median s':>{_COL_MED_S}} "
        f"{'mean MiB/s':>{_COL_MEAN_MIB}} "
        f"{'median MiB/s':>{_COL_MED_MIB}} "
        f"{'mean lines/s':>{_COL_MEAN_LPS}} "
        f"{'peak mem':>{_COL_PEAK}}"
    )

    lines = ["", sep, header, thin]
    for row in rows:
        lines.append(
            f"{row.case_name:<{_COL_CASE}} "
            f"{row.decoded_bytes / MiB:>{_COL_MIB}.2f} "
            f"{row.line_count:>{_COL_LINES},d} "
            f"{row.mean_duration_seconds:>{_COL_MEAN_S}.4f} "
            f"{row.median_duration_seconds:>{_COL_MED_S}.4f} "
            f"{row.mean_throughput_mib_per_sec:>{_COL_MEAN_MIB}.2f} "
            f"{row.median_throughput_mib_per_sec:>{_COL_MED_MIB}.2f} "
            f"{row.mean_lines_per_sec:>{_COL_MEAN_LPS},.0f} "
            f"{format_bytes(row.peak_memory_bytes_max):>{_COL_PEAK}}"
        )
    lines.append(sep)
    return "\n".join(lines)


def render_table_file(
    summaries: list[CaseSummary],
    config: LineStreamerConfig,
    repeats: int,
    timestamp: str,
) -> str:
    """
    Render the summary table with a config header for saving to a file.

    Args:
        summaries:  Benchmark case summaries.
        config:     Streamer config used for this run.
        repeats:    Number of timed runs per case.
        timestamp:  ISO-8601 UTC timestamp string for the header.
    """
    header_lines = [
        "zip-logstream Benchmark Results",
        "=" * 30,
        f"Run at:        {timestamp}",
        f"chunk_size:    {config.chunk_size:,} bytes",
        f"max_line_bytes:{config.max_line_bytes:,} bytes",
        f"encoding:      {config.encoding}",
        f"errors:        {config.errors}",
        f"repeats:       {repeats}",
    ]
    return "\n".join(header_lines) + render_summary_table(summaries) + "\n"


# ---------------------------------------------------------------------------
# Progress output helpers
# ---------------------------------------------------------------------------


def print_case_header(case: BenchmarkCase, file: IO[str] = sys.stdout) -> None:
    """Print a readable heading for one benchmark case."""
    print(file=file)
    print(f"[{case.name}]", file=file)
    print(case.description, file=file)


def print_run_metrics(metrics: RunMetrics, file: IO[str] = sys.stdout) -> None:
    """Print one run's metrics to *file*."""
    print(format_run_metrics(metrics), file=file)


# ---------------------------------------------------------------------------
# CLI and entry point
# ---------------------------------------------------------------------------


def resolve_cases(selected_names: list[str] | None) -> list[BenchmarkCase]:
    """Resolve case name strings to benchmark definitions, or return all defaults."""
    if not selected_names:
        return list(DEFAULT_CASES)

    case_map = {case.name: case for case in DEFAULT_CASES}
    missing = [name for name in selected_names if name not in case_map]
    if missing:
        available = ", ".join(sorted(case_map))
        raise SystemExit(
            f"Unknown benchmark case(s): {', '.join(missing)}. "
            f"Available: {available}"
        )
    return [case_map[name] for name in selected_names]


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Benchmark end-to-end ZIP member streaming with zip-logstream.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--case",
        action="append",
        dest="cases",
        metavar="NAME",
        help="Benchmark case name to run. May be repeated. Defaults to all cases.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=3,
        metavar="N",
        help="Number of timed runs per case.",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1 << 20,
        metavar="BYTES",
        help="LineStreamerConfig.chunk_size in bytes.",
    )
    parser.add_argument(
        "--max-line-bytes",
        type=int,
        default=32 * (1 << 20),
        metavar="BYTES",
        help="LineStreamerConfig.max_line_bytes in bytes.",
    )
    parser.add_argument(
        "--encoding",
        default="utf-8",
        help="Text encoding for generated payloads and streaming.",
    )
    parser.add_argument(
        "--errors",
        default="replace",
        help="Decode error handler passed to LineStreamerConfig.",
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        metavar="DIR",
        help=(
            "Directory for generated benchmark ZIP files. "
            "If omitted, a temporary directory is used and cleaned up afterward."
        ),
    )
    parser.add_argument(
        "--track-memory",
        action="store_true",
        help="Track peak Python memory with tracemalloc.",
    )
    parser.add_argument(
        "--table-out",
        type=Path,
        metavar="PATH",
        help="Save the summary table as plain text to PATH (includes config header).",
    )
    parser.add_argument(
        "--json-out",
        type=Path,
        metavar="PATH",
        help="Save full per-run benchmark data as JSON to PATH.",
    )
    return parser


def main() -> int:
    """Entry point."""
    parser = build_arg_parser()
    args = parser.parse_args()

    if args.repeat <= 0:
        raise SystemExit("--repeat must be greater than 0")

    config = LineStreamerConfig(
        chunk_size=args.chunk_size,
        encoding=args.encoding,
        errors=args.errors,
        max_line_bytes=args.max_line_bytes,
    )
    cases = resolve_cases(args.cases)

    json_payload: dict[str, object] = {
        "config": {
            "chunk_size": config.chunk_size,
            "encoding": config.encoding,
            "errors": config.errors,
            "max_line_bytes": config.max_line_bytes,
        },
        "cases": [],
    }

    summaries: list[CaseSummary] = []

    def execute(workspace: Path) -> None:
        for case in cases:
            print_case_header(case)

            zip_path = workspace / f"{case.name}.zip"
            create_zip_payload(
                zip_path=zip_path,
                member_name=case.member_name,
                text=case.content_factory(),
                encoding=config.encoding,
            )

            runs: list[RunMetrics] = []
            for run_index in range(args.repeat):
                metrics = run_single_benchmark(
                    zip_path=zip_path,
                    target=Path(case.member_name).name,
                    config=config,
                    track_memory=args.track_memory,
                    run_index=run_index,
                    case_name=case.name,
                )
                runs.append(metrics)
                print_run_metrics(metrics)

            summary = summarize_case(case, runs)
            summaries.append(summary)

            json_payload["cases"].append(  # type: ignore[union-attr]
                {
                    "case": {
                        "name": case.name,
                        "description": case.description,
                        "member_name": case.member_name,
                    },
                    "runs": [asdict(run) for run in runs],
                    "summary": asdict(summary),
                }
            )

    if args.workspace is not None:
        args.workspace.mkdir(parents=True, exist_ok=True)
        execute(args.workspace)
    else:
        with TemporaryDirectory(prefix="zip-logstream-bench-") as tmpdir:
            execute(Path(tmpdir))

    # Print summary table to stdout.
    table_text = render_summary_table(summaries)
    print(table_text)

    # Optionally save the summary table with a config header.
    if args.table_out is not None:
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        file_text = render_table_file(summaries, config, args.repeat, timestamp)
        args.table_out.parent.mkdir(parents=True, exist_ok=True)
        args.table_out.write_text(file_text, encoding="utf-8")
        print(f"\nWrote table to: {args.table_out}")

    # Optionally save full per-run JSON.
    if args.json_out is not None:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(json_payload, indent=2), encoding="utf-8")
        print(f"Wrote JSON to:  {args.json_out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
