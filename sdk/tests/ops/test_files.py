"""Tests for the file operations module."""

from pathlib import Path

from spectrumx.ops.files import get_file_permissions


def test_get_file_permissions(temp_file_empty: Path) -> None:
    """Test get_file_permissions for many permission combinations."""
    chmod_combos = {
        "---------": 0o000,
        "--------x": 0o001,
        "r-xr-xr--": 0o554,
        "r--rw-r--": 0o464,
        "rw-rw-r--": 0o664,
        "rwx------": 0o700,
        "rwxrwxrwx": 0o777,
    }
    for perm_string, chmod in chmod_combos.items():
        temp_file_empty.chmod(chmod)
        assert get_file_permissions(temp_file_empty) == perm_string
