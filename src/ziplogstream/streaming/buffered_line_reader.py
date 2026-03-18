"""
ziplogstream.streaming.buffered_line_reader
==========================================

Buffered line reader for chunked binary streams.

Overview
--------
This module provides the low-level streaming engine that converts a
binary input stream into decoded text lines with bounded memory usage.

It is intentionally independent from ZIP-specific archive handling. Any
binary stream object that satisfies `IO[bytes]` can be used as the source.

Public contract
---------------
`BufferedLineReader.iter_lines()` yields decoded `str` values one at a
time without trailing newline characters.

Behavior guarantees
-------------------
- Lines are split on the newline byte (``b"\\n"``).
- If a line ends with CRLF (``b"\\r\\n"``), the trailing ``b"\\r"`` is removed.
- If the input ends with a final partial line lacking ``b"\\n"``, that line
  is still emitted.
- If an unterminated line grows beyond ``max_line_bytes``, the current
  buffer is force-flushed as a decoded chunk and cleared to prevent
  unbounded memory growth.

Design goals
------------
- Bounded memory usage for very large files
- Streaming-only, single-pass operation
- No ZIP-specific logic
- Clear, testable behavior for edge cases

Notes
-----
Oversized buffer flushing is intentionally conservative: when a buffer is
force-flushed due to ``max_line_bytes``, no trailing carriage return is
removed because the flushed content may not represent the end of a logical line.

Performance note
----------------
The CRLF check and byte decoding are inlined directly in the hot loop
rather than delegated to helper functions. This eliminates per-line
Python function call overhead, which is the dominant cost at high line
counts (e.g. 1M+ short lines).
"""

from __future__ import annotations

import logging
from typing import IO, Iterator

from ziplogstream.config import LineStreamerConfig

logger = logging.getLogger(__name__)


class BufferedLineReader:
    """
    Stream decoded text lines from a binary input stream.

    Args:
        raw:
            Binary stream to read from. Must satisfy ``IO[bytes]`` — any
            object with a ``.read(n: int) -> bytes`` method works, including
            ``ZipExtFile``, ``BytesIO``, and buffered file objects.

        config:
            Streaming configuration controlling chunk size, text decoding,
            and the maximum buffered bytes allowed for an unterminated line.
    """

    def __init__(self, raw: IO[bytes], config: LineStreamerConfig) -> None:
        self.raw = raw
        self.config = config

    def iter_lines(self) -> Iterator[str]:
        """
        Iterate decoded text lines from the underlying binary stream.

        Overview
        --------
        Reads binary data in fixed-size chunks, finds line boundaries by
        scanning for the newline byte (``b"\\n"``), normalizes CRLF endings,
        and yields one decoded text line at a time.

        Yield semantics
        ---------------
        - Each yielded value is a decoded ``str`` with no trailing newline.
        - CRLF lines (``\\r\\n``) have the trailing ``\\r`` removed.
        - A final partial line with no trailing newline is still emitted.

        Oversized line behavior
        -----------------------
        If appending the next chunk would cause the buffer to exceed
        ``config.max_line_bytes``, the current buffer is force-flushed as
        a decoded chunk and cleared before the extend. No carriage return
        is stripped during a forced flush because the buffer may be mid-line.

        Yields:
            One decoded text line at a time.
        """
        cfg = self.config

        # Bind hot-path values locally to avoid repeated attribute lookups
        # inside the tight inner loop.
        chunk_size = cfg.chunk_size
        encoding = cfg.encoding
        errors = cfg.errors
        max_line_bytes = cfg.max_line_bytes

        # The byte buffer accumulates unprocessed data between chunk reads.
        # It grows until line boundaries are found or an oversized flush fires.
        buffer = bytearray()

        # Bind read directly to avoid attribute lookup on every chunk.
        read = self.raw.read

        while True:
            chunk = read(chunk_size)
            if not chunk:
                break

            # --- Oversized line guard ---
            # Flush the partial-line buffer before extending so the buffer
            # never exceeds max_line_bytes. No CR stripping here: the buffer
            # may hold only part of a logical line.
            if len(buffer) + len(chunk) > max_line_bytes:
                logger.warning(
                    "Oversized line buffer exceeded %d bytes; flushing chunk.",
                    max_line_bytes,
                )
                yield buffer.decode(encoding, errors)
                buffer.clear()

            buffer.extend(chunk)
            start = 0

            # --- Inner line-scan loop ---
            # Walk forward through the buffer finding newline positions.
            # CRLF check and decode are inlined here (no helper function
            # calls) to eliminate per-line Python frame overhead at high
            # line counts.
            while True:
                newline_pos = buffer.find(b"\n", start)
                if newline_pos == -1:
                    break

                line_bytes = buffer[start:newline_pos]

                # Strip a trailing \r to normalize CRLF line endings.
                if line_bytes.endswith(b"\r"):
                    line_bytes = line_bytes[:-1]

                yield line_bytes.decode(encoding, errors)
                start = newline_pos + 1

            # Drop the consumed portion of the buffer in one operation.
            if start:
                del buffer[:start]

        # --- Final partial line ---
        # Emit any remaining bytes as the last line, even without a trailing
        # newline. Strip a trailing \r here since this is a true line end.
        if buffer:
            if buffer.endswith(b"\r"):
                buffer = buffer[:-1]
            yield buffer.decode(encoding, errors)
