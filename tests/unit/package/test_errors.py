"""
tests.unit.package.test_errors
==============================

Unit tests for :mod:`ziplogstream.errors`.

Overview
--------
This module verifies the public exception hierarchy exported by the
ziplogstream package.

The exception hierarchy is a stable part of the public API: callers rely
on catching ``ZipLogStreamError`` to handle any error from this library
without needing to import each subclass individually. These tests lock in
that contract.

Behavior under test
-------------------
The error classes are expected to:

- all inherit from ``ZipLogStreamError``
- be catchable by the base class
- carry the message string passed at construction
"""

from __future__ import annotations

import pytest

from ziplogstream.errors import (
    ConfigurationError,
    ZipLogStreamError,
    ZipMemberAmbiguityError,
    ZipMemberNotFoundError,
    ZipValidationError,
)

# ---------------------------------------------------------------------------
# Inheritance
# ---------------------------------------------------------------------------


def test_configuration_error_is_a_zip_log_stream_error() -> None:
    assert issubclass(ConfigurationError, ZipLogStreamError)


def test_zip_validation_error_is_a_zip_log_stream_error() -> None:
    assert issubclass(ZipValidationError, ZipLogStreamError)


def test_zip_member_not_found_error_is_a_zip_log_stream_error() -> None:
    assert issubclass(ZipMemberNotFoundError, ZipLogStreamError)


def test_zip_member_ambiguity_error_is_a_zip_log_stream_error() -> None:
    assert issubclass(ZipMemberAmbiguityError, ZipLogStreamError)


# ---------------------------------------------------------------------------
# Base-class catching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigurationError,
        ZipValidationError,
        ZipMemberNotFoundError,
        ZipMemberAmbiguityError,
    ],
)
def test_all_subclasses_are_caught_by_base_class(exc_cls: type) -> None:
    """
    Ensure every subclass is catchable via ``ZipLogStreamError``.

    This verifies the documented contract that callers can use a single
    ``except ZipLogStreamError`` clause to catch any error from the library.
    """
    with pytest.raises(ZipLogStreamError):
        raise exc_cls("test message")


# ---------------------------------------------------------------------------
# Message passing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "exc_cls",
    [
        ConfigurationError,
        ZipValidationError,
        ZipMemberNotFoundError,
        ZipMemberAmbiguityError,
    ],
)
def test_exception_message_is_preserved(exc_cls: type) -> None:
    """
    Ensure the message string passed at construction is accessible via
    ``str()`` on the raised exception.
    """
    with pytest.raises(exc_cls, match="expected message"):
        raise exc_cls("expected message")
