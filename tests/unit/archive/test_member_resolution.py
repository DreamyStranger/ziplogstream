"""
tests.unit.archive.test_member_resolution
=========================================

Unit tests for :mod:`zip_logstream.archive.member_resolution`.

Overview
--------
This module verifies the two public functions in the member resolution
module:

- `default_zip_member_resolver`: the default deterministic member selector
- `resolve_zip_member_name`: the higher-level helper that combines path
  validation, archive opening, and member resolution into one call

Behavior under test
-------------------
`default_zip_member_resolver` is expected to:

- prefer exact basename matches when the target does not contain ``/``
- fall back to suffix matching when no basename match exists
- raise a package-specific not-found error when nothing matches
- raise a package-specific ambiguity error when multiple matches exist
- reject empty and non-string target selectors

`resolve_zip_member_name` is expected to:

- return the normalized path and resolved member name on success
- accept both ``Path`` and string archive path inputs
- honor caller-provided resolver functions
- propagate validation and resolution failures unchanged

Test philosophy
---------------
These are focused unit tests. They exercise member selection logic against
small temporary ZIP archives and do not test the higher-level streaming
pipeline.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from zip_logstream import ZipMemberAmbiguityError, ZipMemberNotFoundError, ZipValidationError
from zip_logstream.archive import default_zip_member_resolver
from zip_logstream.archive.member_resolution import resolve_zip_member_name


def test_resolver_prefers_exact_basename_match_when_target_is_plain_filename(
    make_zip,
) -> None:
    """
    Ensure basename matching is preferred when the target contains no path
    separator.

    If the caller provides a plain filename such as ``"app.log"``, the
    resolver should first search for members whose basename is exactly that
    value, rather than immediately applying broader suffix matching.
    """
    zip_path = make_zip(
        "basename_match.zip",
        {
            "logs/app.log": b"a\n",
            "logs/app.log.1": b"b\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        resolved = default_zip_member_resolver(zf, "app.log")

    assert resolved == "logs/app.log"


def test_resolver_falls_back_to_suffix_match_when_no_basename_match_exists(
    make_zip,
) -> None:
    """
    Ensure suffix matching is used when basename matching does not produce
    a result.

    This protects the documented fallback behavior that allows callers to
    specify nested suffixes such as ``"service/app.log"``.
    """
    zip_path = make_zip(
        "suffix_match.zip",
        {
            "nested/path/service/app.log": b"a\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        resolved = default_zip_member_resolver(zf, "service/app.log")

    assert resolved == "nested/path/service/app.log"


def test_resolver_raises_not_found_when_no_member_matches_target(make_zip) -> None:
    """
    Ensure a missing target raises ``ZipMemberNotFoundError``.

    The error should be explicit rather than silently returning an arbitrary
    member or falling back to unrelated archive contents.
    """
    zip_path = make_zip(
        "not_found.zip",
        {
            "logs/app.log": b"a\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(ZipMemberNotFoundError, match="missing.log"):
            default_zip_member_resolver(zf, "missing.log")


def test_resolver_raises_ambiguity_when_multiple_basename_matches_exist(
    make_zip,
) -> None:
    """
    Ensure duplicate basename matches are treated as an error.

    When multiple archive members share the same basename, the resolver
    must fail explicitly rather than guessing which file the caller meant.
    """
    zip_path = make_zip(
        "ambiguous_basename.zip",
        {
            "a/app.log": b"a\n",
            "b/app.log": b"b\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(ZipMemberAmbiguityError, match="Ambiguous target"):
            default_zip_member_resolver(zf, "app.log")


def test_resolver_raises_ambiguity_when_multiple_suffix_matches_exist(
    make_zip,
) -> None:
    """
    Ensure duplicate suffix matches are treated as an error.

    This verifies that the fallback suffix-based resolution path remains
    deterministic by failing on ambiguity instead of choosing one match
    implicitly.
    """
    zip_path = make_zip(
        "ambiguous_suffix.zip",
        {
            "x/service/app.log": b"a\n",
            "y/service/app.log": b"b\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(ZipMemberAmbiguityError, match="Ambiguous target"):
            default_zip_member_resolver(zf, "service/app.log")


def test_resolver_rejects_empty_target_selector(make_zip) -> None:
    """
    Ensure an empty target selector is rejected.

    An empty string is not a meaningful archive member selector and should
    fail immediately with a package-specific error.
    """
    zip_path = make_zip(
        "empty_target.zip",
        {
            "logs/app.log": b"a\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(
            ZipValidationError,
            match="Target member selector must be a non-empty string",
        ):
            default_zip_member_resolver(zf, "")


def test_resolver_rejects_non_string_target(make_zip) -> None:
    """
    Ensure non-string target values are rejected.

    The resolver's type guard (``isinstance(target, str)``) should catch
    callers that pass ``None``, integers, or other non-string values.
    """
    zip_path = make_zip(
        "non_string_target.zip",
        {
            "logs/app.log": b"a\n",
        },
    )

    with zipfile.ZipFile(zip_path, "r") as zf:
        with pytest.raises(
            ZipValidationError,
            match="Target member selector must be a non-empty string",
        ):
            default_zip_member_resolver(zf, None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_zip_member_name
# ---------------------------------------------------------------------------


def test_resolve_zip_member_name_returns_normalized_path_and_member_name(
    make_text_zip,
) -> None:
    """
    Ensure the helper returns both the normalized archive path and the
    resolved member name.
    """
    zip_path = make_text_zip("resolve.zip", {"logs/app.log": "alpha\nbeta\n"})

    normalized_path, member_name = resolve_zip_member_name(
        zip_path, "app.log", resolver=default_zip_member_resolver
    )

    assert normalized_path == Path(zip_path)
    assert member_name == "logs/app.log"


def test_resolve_zip_member_name_accepts_string_path(make_text_zip) -> None:
    """
    Ensure string archive paths are accepted and normalized to ``Path``.
    """
    zip_path = make_text_zip("resolve_string.zip", {"logs/app.log": "alpha\n"})

    normalized_path, member_name = resolve_zip_member_name(
        str(zip_path), "app.log", resolver=default_zip_member_resolver
    )

    assert normalized_path == Path(zip_path)
    assert member_name == "logs/app.log"


def test_resolve_zip_member_name_uses_custom_resolver(make_text_zip) -> None:
    """
    Ensure the caller-provided resolver is used for member selection.
    """
    zip_path = make_text_zip(
        "custom_resolver.zip",
        {"logs/app.log": "alpha\n", "logs/other.log": "beta\n"},
    )

    def resolver(zf: zipfile.ZipFile, target: str) -> str:
        return "logs/other.log"

    normalized_path, member_name = resolve_zip_member_name(
        zip_path, "ignored.log", resolver=resolver
    )

    assert normalized_path == Path(zip_path)
    assert member_name == "logs/other.log"


def test_resolve_zip_member_name_raises_for_missing_archive(tmp_path: Path) -> None:
    """
    Ensure archive validation failures propagate unchanged.
    """
    with pytest.raises(FileNotFoundError, match="ZIP not found"):
        resolve_zip_member_name(
            tmp_path / "missing.zip", "app.log", resolver=default_zip_member_resolver
        )


def test_resolve_zip_member_name_raises_for_non_zip_file_contents(
    tmp_path: Path,
) -> None:
    """
    Ensure non-ZIP file contents are rejected when archive opening begins.
    """
    path = tmp_path / "not_a_zip.txt"
    path.write_text("hello", encoding="utf-8")

    with pytest.raises(ZipValidationError, match="Invalid or corrupt ZIP archive"):
        resolve_zip_member_name(path, "app.log", resolver=default_zip_member_resolver)


def test_resolve_zip_member_name_raises_when_member_cannot_be_resolved(
    make_text_zip,
) -> None:
    """
    Ensure member resolution failures propagate unchanged.
    """
    zip_path = make_text_zip("missing_member.zip", {"logs/app.log": "alpha\n"})

    with pytest.raises(ZipMemberNotFoundError):
        resolve_zip_member_name(
            zip_path, "missing.log", resolver=default_zip_member_resolver
        )


def test_resolve_zip_member_name_raises_zip_validation_error_for_corrupt_archive(
    tmp_path: Path,
) -> None:
    """
    Ensure a corrupt archive raises ``ZipValidationError`` rather than
    leaking ``zipfile.BadZipFile``, and that the original exception is
    chained as ``__cause__``.
    """
    corrupt_zip = tmp_path / "corrupt.zip"
    corrupt_zip.write_bytes(b"this is not a valid zip file")

    with pytest.raises(ZipValidationError, match="Invalid or corrupt ZIP archive") as exc_info:
        resolve_zip_member_name(
            corrupt_zip, "app.log", resolver=default_zip_member_resolver
        )

    assert isinstance(exc_info.value.__cause__, zipfile.BadZipFile)
