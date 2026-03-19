"""
tests.unit.streaming.test_line_streamer
=============================

Unit tests for :mod:`zipstreamer.streaming.line_streamer`.

Overview
--------
This module verifies the behavior of the high-level
:class:`zipstreamer.streaming.line_streamer.LineStreamer` API.

Unlike lower-level tests for the streaming engine or resolver logic,
these tests focus on the orchestration responsibilities of the
``LineStreamer`` class:

- validating archive paths
- resolving the correct archive member
- streaming decoded lines from that member
- honoring custom configuration and resolver behavior

Behavior under test
-------------------
The ``LineStreamer`` class is expected to:

- stream lines from a resolved ZIP archive member
- accept both ``str`` and ``Path`` archive inputs
- respect configuration options such as chunk size
- allow caller-provided resolver functions
- raise explicit exceptions when resolution fails

Test philosophy
---------------
These tests operate on small temporary ZIP archives created during test
execution. They validate the high-level orchestration logic without
duplicating the detailed behavior already covered by lower-level unit
tests.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from zip_logstream import LineStreamer, LineStreamerConfig
from zip_logstream.errors import ZipMemberNotFoundError, ZipValidationError


def test_streamer_streams_lines_from_zip_member(make_text_zip) -> None:
    """
    Ensure the streamer yields decoded lines from the resolved archive
    member.
    """
    zip_path = make_text_zip(
        "basic.zip",
        {
            "logs/app.log": "alpha\nbeta\ngamma\n",
        },
    )

    streamer = LineStreamer(zip_path, "app.log")

    assert list(streamer.stream()) == ["alpha", "beta", "gamma"]


def test_streamer_accepts_string_archive_path(make_text_zip) -> None:
    """
    Ensure a string path can be provided instead of a ``Path`` instance.
    """
    zip_path = make_text_zip(
        "string_path.zip",
        {
            "logs/app.log": "hello\nworld\n",
        },
    )

    streamer = LineStreamer(str(zip_path), "app.log")

    assert list(streamer.stream()) == ["hello", "world"]


def test_streamer_respects_custom_configuration(make_text_zip) -> None:
    """
    Ensure caller-provided configuration values are honored by the
    streaming pipeline.
    """
    zip_path = make_text_zip(
        "custom_config.zip",
        {
            "logs/app.log": "abcdef\n123456\nxyz\n",
        },
    )

    cfg = LineStreamerConfig(chunk_size=2)

    streamer = LineStreamer(zip_path, "app.log", config=cfg)

    assert list(streamer.stream()) == ["abcdef", "123456", "xyz"]


def test_streamer_uses_custom_resolver(make_text_zip) -> None:
    """
    Ensure a caller-provided resolver is used instead of the default
    resolution strategy.
    """
    zip_path = make_text_zip(
        "custom_resolver.zip",
        {
            "logs/service.log": "alpha\nbeta\n",
        },
    )

    def resolver(zf, target: str) -> str:
        return "logs/service.log"

    streamer = LineStreamer(zip_path, "ignored.log", resolver=resolver)

    assert list(streamer.stream()) == ["alpha", "beta"]


def test_streamer_raises_when_member_not_found(make_text_zip) -> None:
    """
    Ensure resolution failure propagates as a package-specific exception.
    """
    zip_path = make_text_zip(
        "missing_member.zip",
        {
            "logs/app.log": "alpha\n",
        },
    )

    streamer = LineStreamer(zip_path, "missing.log")

    with pytest.raises(ZipMemberNotFoundError):
        list(streamer.stream())


def test_streamer_supports_path_objects(make_text_zip) -> None:
    """
    Ensure ``Path`` inputs behave identically to string inputs.
    """
    zip_path = make_text_zip(
        "path_object.zip",
        {
            "logs/app.log": "alpha\nbeta\n",
        },
    )

    streamer = LineStreamer(Path(zip_path), "app.log")

    assert list(streamer.stream()) == ["alpha", "beta"]


def test_streamer_raises_file_not_found_when_zip_does_not_exist(
    tmp_path: Path,
) -> None:
    """
    Ensure ``FileNotFoundError`` is raised by ``stream()`` when the archive
    path does not exist on disk.

    This verifies that path validation inside ``stream()`` fires correctly
    through the public ``LineStreamer`` API, not just the validator layer.
    """
    streamer = LineStreamer(tmp_path / "missing.zip", "app.log")

    with pytest.raises(FileNotFoundError):
        list(streamer.stream())


def test_streamer_accepts_valid_zip_file_with_non_zip_suffix(
    tmp_path: Path,
) -> None:
    """
    Ensure ``stream()`` accepts valid ZIP payloads regardless of filename
    suffix.
    """
    path = tmp_path / "archive.tar"

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("logs/app.log", b"alpha\nbeta\n")

    streamer = LineStreamer(path, "app.log")

    assert list(streamer.stream()) == ["alpha", "beta"]


def test_streamer_yields_empty_iterator_for_empty_member(make_zip) -> None:
    """
    Ensure an archive member with zero bytes yields no lines.
    """
    zip_path = make_zip("empty_member.zip", {"logs/app.log": b""})

    streamer = LineStreamer(zip_path, "app.log")

    assert list(streamer.stream()) == []


def test_streamer_raises_zip_validation_error_for_corrupt_archive(
    tmp_path: Path,
) -> None:
    """
    Ensure ``ZipValidationError`` is raised when the archive is corrupt,
    not a raw ``zipfile.BadZipFile``, and that the original exception is
    chained as ``__cause__``.
    """
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"this is not a valid zip file")

    streamer = LineStreamer(corrupt_zip, "app.log")

    with pytest.raises(ZipValidationError, match="Invalid or corrupt ZIP archive") as exc_info:
        list(streamer.stream())

    assert isinstance(exc_info.value.__cause__, zipfile.BadZipFile)


def test_streamer_raises_member_not_found_when_custom_resolver_returns_bad_name(
    make_text_zip,
) -> None:
    """
    Ensure ``ZipMemberNotFoundError`` is raised (not a bare ``KeyError``)
    when a custom resolver returns a member name that does not exist in the
    archive.
    """
    zip_path = make_text_zip("bad_resolver.zip", {"logs/app.log": "alpha\n"})

    def bad_resolver(zf: zipfile.ZipFile, target: str) -> str:
        return "nonexistent/member.log"

    streamer = LineStreamer(zip_path, "app.log", resolver=bad_resolver)

    with pytest.raises(ZipMemberNotFoundError, match="nonexistent/member.log"):
        list(streamer.stream())


def test_streamer_stream_can_be_called_multiple_times(make_text_zip) -> None:
    """
    Ensure calling ``stream()`` more than once on the same ``LineStreamer``
    instance produces the same result each time.

    ``stream()`` creates a fresh generator on each call, so repeated calls
    must not exhaust or corrupt internal state.
    """
    zip_path = make_text_zip(
        "multi_stream.zip",
        {
            "logs/app.log": "alpha\nbeta\n",
        },
    )

    streamer = LineStreamer(zip_path, "app.log")

    assert list(streamer.stream()) == ["alpha", "beta"]
    assert list(streamer.stream()) == ["alpha", "beta"]
