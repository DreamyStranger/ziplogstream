"""
zip_logstream.protocols
======================

Protocol definitions for public extension points.

Overview
--------
This module defines structural typing contracts used across the
zip-logstream package. The goal is to make extension points explicit,
well-documented, and friendly to static type checkers.

At present, the primary extension point is ZIP member resolution:
given an open `zipfile.ZipFile` and a user-provided target selector,
return exactly one member name to stream.

Design goals
------------
- Keep extension points small and stable
- Support user-defined callables without requiring inheritance
- Improve readability of public APIs through named protocols

Notes
-----
A resolver is intentionally defined as a protocol rather than a concrete
base class. Any callable with a compatible signature satisfies the
contract, which means plain functions, lambdas, and class instances all
work without importing this module.
"""

from __future__ import annotations

import zipfile
from typing import Protocol


class ZipMemberResolver(Protocol):
    """
    Callable protocol for resolving a single member inside a ZIP archive.

    A resolver receives an open `zipfile.ZipFile` and a user-provided
    target selector string. It must return the exact archive member name
    to open, or raise a meaningful exception if the target cannot be
    resolved.

    Implementations are free to use any matching strategy, such as exact
    member name matching, basename matching, suffix matching, or
    metadata-driven selection. The default implementation is
    `default_zip_member_resolver`.

    Args:
        zf:
            An open ZIP archive instance.

        target:
            A caller-provided selector string, such as a filename or suffix.

    Returns:
        The exact member name to open from the archive.
    """

    def __call__(self, zf: zipfile.ZipFile, target: str) -> str: ...
