"""Common test fixtures and utilities for the SDS SDK."""

import os
import random
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from loguru import logger as log
from spectrumx import enable_logging
from spectrumx.utils import get_random_line

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    log.warning("Install rich for better tracebacks")

enable_logging()


# ==== fixtures


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


@pytest.fixture
def temp_file_with_text_contents(tmp_path: Path) -> Generator[Path]:
    """Fixture for a file with contents."""
    file_path = (
        tmp_path / f"test_file_{get_random_line(6, include_punctuation=False)}.txt"
    )
    # generate random string to change checksums every time
    with file_path.open("w", encoding="utf-8") as file_handle:
        file_handle.writelines(file_content_generator())

    yield file_path

    file_path.unlink(missing_ok=True)


@pytest.fixture
@pytest.mark.slow
def temp_large_binary_file(
    tmp_path: Path,
    target_size_mb: int | None = None,
) -> Generator[Path]:
    """Fixture to create a temporary large binary file."""
    if target_size_mb is None:
        target_size_mb = random.randint(10, 20)  # noqa: S311
    large_binary_file = tmp_path / "large_binary_file"
    byte_generator = random_bytes_generator(1024 * 1024 * target_size_mb)
    with large_binary_file.open("wb") as f_ptr:
        for chunk in byte_generator:
            f_ptr.write(chunk)

    yield large_binary_file

    large_binary_file.unlink(missing_ok=True)


@pytest.fixture
def temp_file_tree(
    tmp_path: Path,
    num_dirs: int = 4,
    num_files_per_dir: int = 4,
) -> Generator[Path]:
    """Fixture to create a temporary directory with files in subdirs."""

    _total_num_files = num_dirs * num_files_per_dir
    _all_created_files: list[Path] = []
    _all_created_dirs: list[Path] = []
    extension: str = ".txt"

    for dir_idx in range(num_dirs):
        subdir = tmp_path / f"subdir_{dir_idx}"
        subdir.mkdir(exist_ok=True)
        _all_created_dirs.append(subdir)
        for file_sub_idx in range(num_files_per_dir):
            file_path = subdir / f"test_file_{file_sub_idx}.{extension}"
            _all_created_files.append(file_path)
            with file_path.open("w", encoding="utf-8") as file_handle:
                file_handle.writelines(file_content_generator())
    assert len(_all_created_files) == _total_num_files

    yield tmp_path

    # cleanup
    for file_path in _all_created_files:
        file_path.unlink(missing_ok=True)
    for dir_path in _all_created_dirs:
        dir_path.rmdir()


# ==== helpers


def random_bytes_generator(size: int, chunk: int = 1024) -> Generator[bytes]:
    """Generates random binary data for tests."""
    for _ in range(size // chunk):
        yield os.urandom(chunk)
    yield os.urandom(size % chunk)


def file_content_generator(
    num_lines: int = 100, chars_per_line: int = 80
) -> Generator[str]:
    """Generator for file content."""
    for _current_line in range(num_lines):
        random_line = get_random_line(chars_per_line)
        yield f"{random_line}\n"
