"""Tests for the client module."""

from pathlib import Path

import pytest
from spectrumx.client import SDSConfig


def test_load_config_env_file_not_found(caplog: pytest.LogCaptureFixture) -> None:
    """Test that a warning is logged when the environment file is not found."""

    non_existent_file = Path("non_existent.env")
    SDSConfig(env_file=non_existent_file)

    assert "file not found" in caplog.text.lower()
