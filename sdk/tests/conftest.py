"""Common test fixtures and utilities for the SDS SDK."""

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    pass

from typing import Any

import pytest
from spectrumx import enable_logging

enable_logging()


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Fixture to create a sample configuration."""
    return {"SDS_SECRET_TOKEN": "12345", "HTTP_TIMEOUT": 42}
