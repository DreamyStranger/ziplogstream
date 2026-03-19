"""
tests.integration.test_error_contract_zip
==========================================

Integration tests for error-contract compliance through the full
``LineStreamer`` pipeline.

These tests verify that the documented exceptions are raised correctly
when driving the complete stack — archive validation, ZIP opening, member
resolution, and streaming — rather than only at the unit level.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from zip_logstream import LineStreamer
from zip_logstream.errors import (
    ZipMemberAmbiguityError,
    ZipMemberNotFoundError,
    ZipValidationError,
)


def test_file_not_found_error_for_missing_archive(tmp_path: Path) -> None:
    """
    Ensure ``FileNotFoundError`` propagates through the full stack when the
    archive path does not exist on disk.
    """
    streamer = LineStreamer(tmp_path / "missing.zip", "app.log")

    with pytest.raises(FileNotFoundError):
        list(streamer.stream())


def test_zip_validation_error_for_corrupt_archive(tmp_path: Path) -> None:
    """
    Ensure ``ZipValidationError`` is raised end-to-end for a corrupt archive,
    not a raw ``zipfile.BadZipFile``.
    """
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"this is not a valid zip file")

    streamer = LineStreamer(corrupt_zip, "app.log")

    with pytest.raises(ZipValidationError, match="Invalid or corrupt ZIP archive") as exc_info:
        list(streamer.stream())

    assert isinstance(exc_info.value.__cause__, zipfile.BadZipFile)


def test_zip_validation_error_for_non_zip_file_contents(tmp_path: Path) -> None:
    """
    Ensure ``ZipValidationError`` is raised end-to-end when the archive path
    points at non-ZIP file contents.
    """
    path = tmp_path / "archive.tar"
    path.write_bytes(b"not a zip")

    streamer = LineStreamer(path, "app.log")

    with pytest.raises(ZipValidationError):
        list(streamer.stream())


def test_member_not_found_error_end_to_end(make_text_zip) -> None:
    """
    Ensure ``ZipMemberNotFoundError`` propagates through the full stack when
    the target member does not exist in the archive.
    """
    zip_path = make_text_zip("member_not_found.zip", {"logs/app.log": "alpha\n"})

    streamer = LineStreamer(zip_path, "missing.log")

    with pytest.raises(ZipMemberNotFoundError):
        list(streamer.stream())


def test_member_ambiguity_error_end_to_end(make_text_zip) -> None:
    """
    Ensure ``ZipMemberAmbiguityError`` propagates through the full stack when
    multiple archive members match the target selector.
    """
    zip_path = make_text_zip(
        "ambiguous.zip",
        {
            "service-a/app.log": "alpha\n",
            "service-b/app.log": "beta\n",
        },
    )

    streamer = LineStreamer(zip_path, "app.log")

    with pytest.raises(ZipMemberAmbiguityError):
        list(streamer.stream())
