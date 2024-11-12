"""Common test fixtures and utilities for the SDS SDK."""

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    pass

from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from spectrumx import enable_logging
from spectrumx.utils import get_random_line

enable_logging()


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Fixture to create a sample configuration."""
    return {"SDS_SECRET_TOKEN": "12345", "HTTP_TIMEOUT": 42}


@pytest.fixture
def temp_file_empty(tmp_path: Path) -> Path:
    """Fixture to create a temporary file for testing."""
    file_path = tmp_path / "empty_test_file.txt"
    file_path.touch()
    return file_path


def file_content_generator(
    num_lines: int = 100, chars_per_line: int = 80
) -> Generator[str, None, None]:
    """Generator for file content."""
    for _current_line in range(num_lines):
        random_line = get_random_line(chars_per_line)
        yield f"{random_line}\n"


@pytest.fixture
def temp_file_with_text_contents(tmp_path: Path) -> Path:
    """Fixture for a file with contents."""
    file_path = (
        tmp_path / f"test_file_{get_random_line(6, include_punctuation=False)}.txt"
    )
    # generate random string to change checksums every time
    with file_path.open("w", encoding="utf-8") as file_handle:
        file_handle.writelines(file_content_generator())
    return file_path


@pytest.fixture
def temp_file_tree(
    tmp_path: Path,
    num_dirs: int = 4,
    num_files_per_dir: int = 4,
) -> Path:
    """Fixture to create a temporary directory with files in subdirs."""

    total_files = num_dirs * num_files_per_dir

    for dir_idx in range(num_dirs):
        subdir = tmp_path / f"subdir_{dir_idx}"
        subdir.mkdir()
        for file_sub_idx in range(num_files_per_dir):
            file_path = subdir / f"test_file_{file_sub_idx}.txt"
            with file_path.open("w", encoding="utf-8") as file_handle:
                file_handle.writelines(file_content_generator())
    assert len(list(tmp_path.rglob("*.txt"))) == total_files
    return tmp_path
