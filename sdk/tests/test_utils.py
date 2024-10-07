"""Tests for the utils module."""

import pytest

from spectrumx import utils


def test_permission_string_invalid_length() -> None:
    """Test that an invalid permission string raises an error."""
    invalid_len = [
        "rwxrwxrwxr",
        "rw-rwxrwxrwx",
        "rwxr-xr",
    ]
    for perm in invalid_len:
        with pytest.raises(AssertionError):
            utils.validate_file_permission_string(perm)


def test_permission_string_invalid_chars() -> None:
    """Test that an invalid permission string raises an error."""
    invalid_chars = [
        "rwxrwxrws",
        "rw_______",
        "rwxrwxrw?",
    ]
    for perm in invalid_chars:
        with pytest.raises(AssertionError):
            utils.validate_file_permission_string(perm)


def test_permission_string_out_of_order() -> None:
    """Test that an invalid permission string raises an error."""
    invalid_order = [
        "rwxrwxwxr",
        "wrxrwxrwx",
        "rwxrxwrwx",
        "--------r",
    ]
    for perm in invalid_order:
        with pytest.raises(AssertionError):
            utils.validate_file_permission_string(perm)


def test_permission_string_valid() -> None:
    """Test that a valid permission string passes."""
    valid_cases = [
        "rwxrwxrwx",
        "rw-rw-r--",
        "r--r--r--",
        "---------",
        "rwx------",
    ]
    for valid in valid_cases:
        utils.validate_file_permission_string(valid)
