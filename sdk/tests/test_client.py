"""Tests for the client module."""

import re
from enum import IntEnum
from pathlib import Path
from typing import Any

import pytest
from spectrumx.client import SDSConfig


class LogLevels(IntEnum):
    """Log levels for testing."""

    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


def test_load_config_env_file_not_found(caplog: pytest.LogCaptureFixture) -> None:
    """When the env file is not found, a warning must be logged."""

    non_existent_file = Path("non_existent.env")
    caplog.set_level(LogLevels.WARNING)
    SDSConfig(env_file=non_existent_file)

    assert "file missing" in caplog.text.lower()


def test_load_config_file_found(caplog: pytest.LogCaptureFixture) -> None:
    """A valid env file must be found and loaded."""

    filename = "existing.env"
    existing_file = Path(filename)
    existing_file.touch()
    caplog.set_level(LogLevels.DEBUG)
    SDSConfig(env_file=existing_file, verbose=True)

    pattern = f"found.*{filename}".lower()
    assert re.search(pattern, caplog.text.lower())
    existing_file.unlink()


def test_load_config_from_args(sample_config: dict[str, Any]) -> None:
    """Ensures loading config from arguments works."""

    config = SDSConfig(env_file=Path(".env.example"), env_config=sample_config)

    assert config.api_key == sample_config["SDS_SECRET_TOKEN"]
    assert config.timeout == sample_config["HTTP_TIMEOUT"]


def test_show_config_does_not_expose_api_key(
    sample_config: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Makes sure the API key is not exposed by show_config()."""

    config = SDSConfig(env_file=Path(".env.example"), env_config=sample_config)
    config.show_config()

    # this all_outputs approach should work for both `make test` and `make test-verbose`
    captured = capsys.readouterr()
    all_outputs = (captured.out + captured.err + caplog.text).lower()

    assert "api_key" in all_outputs
    assert sample_config["SDS_SECRET_TOKEN"] not in all_outputs


def test_warning_for_unrecognized_config(
    sample_config: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """A warning must be logged for unrecognized configuration."""

    unknown_attr = "UNRECOGNIZED_CONFIG"
    sample_config[unknown_attr] = "value"
    caplog.set_level(LogLevels.WARNING)
    SDSConfig(env_file=Path(".env.example"), env_config=sample_config)

    assert "not recognized" in caplog.text.lower()
    assert unknown_attr in caplog.text
