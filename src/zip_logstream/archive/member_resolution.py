"""
zip_logstream.archive.member_resolution
=====================================

Deterministic ZIP member resolution strategies.

Overview
--------
This module provides logic for resolving a single target member from an
open ZIP archive, and a higher-level helper that combines path validation
with member resolution.

Public contract
---------------
`default_zip_member_resolver` operates on an already-open `zipfile.ZipFile`
and returns the exact member name to read.

`resolve_zip_member_name` is an internal helper that combines path
validation, archive opening, and member resolution into a single call.
It is not part of the public API.

The default resolver follows a deterministic strategy:
    1. If the target contains no '/' characters, prefer exact basename
       matches across all members.
    2. If no basename match is found, fall back to suffix matching via
       `member_name.endswith(target)`.
    3. If no members match, raise `ZipMemberNotFoundError`.
    4. If multiple members match, raise `ZipMemberAmbiguityError`.

Design goals
------------
- Deterministic behavior
- Explicit ambiguity failures
- Minimal policy surface
- Easy replacement with custom resolvers

This module does not stream bytes or decode text.
"""

from __future__ import annotations

import zipfile
from collections.abc import Sequence
from pathlib import Path

from zip_logstream.errors import ZipMemberAmbiguityError, ZipMemberNotFoundError, ZipValidationError
from zip_logstream.protocols import ZipMemberResolver

from .validators import normalize_zip_path, validate_zip_path


def default_zip_member_resolver(zf: zipfile.ZipFile, target: str) -> str:
    """
    Resolve a unique target member inside a ZIP archive.

    Resolution strategy:
        1. If `target` contains no '/' characters, prefer exact basename
           matches. For example, target="app.log" matches members whose
           basename is exactly "app.log", such as "logs/app.log".
        2. If no basename matches are found, fall back to suffix matching
           using `member_name.endswith(target)`.
        3. If no matches exist, raise `ZipMemberNotFoundError`.
        4. If multiple matches exist, raise `ZipMemberAmbiguityError`.

    Args:
        zf:
            Open ZIP archive instance.

        target:
            Filename or suffix identifying the desired member.

    Returns:
        The resolved archive member name.

    Raises:
        ZipValidationError:
            If ``target`` is not a non-empty string.

        ZipMemberNotFoundError:
            If no archive member matches the target.

        ZipMemberAmbiguityError:
            If the target matches more than one archive member.
    """
    if not isinstance(target, str) or not target:
        raise ZipValidationError("Target member selector must be a non-empty string")

    names: Sequence[str] = zf.namelist()
    matches: list[str] = []

    if "/" not in target:
        basename_matches = [name for name in names if name.rsplit("/", 1)[-1] == target]
        if basename_matches:
            matches = basename_matches

    if not matches:
        matches = [name for name in names if name.endswith(target)]

    if not matches:
        zip_name = getattr(zf, "filename", "<zip>")
        raise ZipMemberNotFoundError(f"'{target}' not found in ZIP: {zip_name}")

    if len(matches) > 1:
        raise ZipMemberAmbiguityError(
            f"Ambiguous target '{target}'. Matches: {matches}"
        )

    return matches[0]


def resolve_zip_member_name(
    zip_path: Path | str,
    target: str,
    *,
    resolver: ZipMemberResolver,
) -> tuple[Path, str]:
    """
    Validate a ZIP path and resolve the exact target member name.

    This helper is useful when the caller needs the normalized archive path
    together with the resolved member name, without streaming the content.
    It combines path normalization, validation, and member resolution into
    a single call.

    Args:
        zip_path:
            Path to the ZIP archive.

        target:
            User-provided member selector string.

        resolver:
            Callable used to resolve `target` to one exact member name.

    Returns:
        A tuple of:
        - normalized ZIP path
        - resolved member name

    Raises:
        FileNotFoundError:
            If the ZIP path does not exist.

        ZipValidationError:
            If the archive path is invalid.

        ZipMemberNotFoundError:
            If the resolver cannot find a matching member.

        ZipMemberAmbiguityError:
            If the resolver finds more than one matching member.
    """
    normalized_path = normalize_zip_path(zip_path)
    validate_zip_path(normalized_path)

    try:
        zf_ctx = zipfile.ZipFile(normalized_path, "r")
    except zipfile.BadZipFile as exc:
        raise ZipValidationError(f"Invalid or corrupt ZIP archive: {normalized_path}") from exc
    with zf_ctx as zf:
        member_name = resolver(zf, target)

    return normalized_path, member_name
