"""
tests.unit.package.test_exports
===============================

Unit tests for the public package export surface.
"""

from __future__ import annotations

from ziplogstream import (
    ConfigurationError,
    LineStreamer,
    LineStreamerConfig,
    ZipLogStreamError,
    ZipMemberAmbiguityError,
    ZipMemberNotFoundError,
    ZipMemberResolver,
    ZipValidationError,
    __version__,
    default_zip_member_resolver,
)


def test_top_level_exports_are_available() -> None:
    """
    Ensure the documented top-level public API is importable from the
    package root.
    """
    assert __version__ is not None
    assert LineStreamer is not None
    assert LineStreamerConfig is not None
    assert ZipMemberResolver is not None
    assert default_zip_member_resolver is not None
    assert ZipLogStreamError is not None
    assert ConfigurationError is not None
    assert ZipValidationError is not None
    assert ZipMemberNotFoundError is not None
    assert ZipMemberAmbiguityError is not None