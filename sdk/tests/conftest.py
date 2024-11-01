"""Common test fixtures and utilities for the SDS SDK."""

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    pass

from pathlib import Path
from typing import Any

import pytest
from spectrumx import enable_logging

enable_logging()


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Fixture to create a sample configuration."""
    return {"SDS_SECRET_TOKEN": "12345", "HTTP_TIMEOUT": 42}


@pytest.fixture
def temp_file_empty(tmp_path: Path) -> Path:
    """Fixture to create a temporary file for testing."""
    file_path = tmp_path / "test_file.txt"
    file_path.touch()
    return file_path


@pytest.fixture
def temp_file_with_text_contents(tmp_path: Path) -> Path:
    """Fixture for a file with contents."""
    file_path = tmp_path / "test_file.txt"
    file_path.write_text("start\n" + "Test file contents. " * 201 + "\nend")
    return file_path
