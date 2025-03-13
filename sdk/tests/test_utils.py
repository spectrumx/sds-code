"""Tests for the utils module."""

from pathlib import Path

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


def test_into_bool_truthy() -> None:
    """Makes sure truthy values are converted to True."""
    truthy_values = [
        True,
        1,
        "true",
        "True",
        "TrUe",
        "TRUE",
        "ON",
        "1",
        "t",
        "y",
        "yes",
        "on",
        "enabled",
    ]
    for truthy in truthy_values:
        assert utils.into_human_bool(truthy) is True, f"{truthy} failed"


@pytest.mark.linux
@pytest.mark.darwin
def test_clean_local_path() -> None:
    """Test that a local path is cleaned."""
    test_cases = [
        {
            # our usual case
            "input": Path("/files/user@domain.com/clean/path"),
            "expected": Path("clean/path"),
        },
        {
            # still clean it when not in a top-level
            "input": Path("files/user@domain.ai/clean/path"),
            "expected": Path("clean/path"),
        },
        {
            # still clean it when not "files"
            "input": Path("___/user@domain.ai/clean/path"),
            "expected": Path("clean/path"),
        },
        {
            # no changes
            "input": Path("example.com/change/path"),
            "expected": Path("example.com/change/path"),
        },
        {
            # no changes
            "input": Path("user@domain.dev/still/clean/path"),
            "expected": Path("user@domain.dev/still/clean/path"),
        },
        {
            # no changes
            "input": Path("yet/another/path"),
            "expected": Path("yet/another/path"),
        },
    ]
    for case in test_cases:
        entered = case["input"]
        expected = case["expected"]
        actual = utils.clean_local_path(entered)
        assert actual == case["expected"], (
            f"Failed: {entered} -> {actual} != {expected}"
        )


def test_into_bool_falsey() -> None:
    """Makes sure falsey values are converted to False."""
    falsey_values = [
        False,
        0,
        "false",
        "False",
        "FalSe",
        "FALSE",
        "OFF",
        "0",
        "f",
        "n",
        "no",
        "off",
        "disabled",
    ]
    for falsey in falsey_values:
        assert utils.into_human_bool(falsey) is False, f"{falsey} failed"
