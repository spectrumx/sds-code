"""Tests for the File model."""

# pylint: disable=redefined-outer-name

from datetime import datetime
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from pytz import UTC
from pytz import timezone
from spectrumx.models.files import File


@pytest.fixture
def file_properties() -> dict[str, Any]:
    """Fixture to create a dictionary of file properties."""
    tz = timezone("UTC")
    return {
        "name": "test_file",
        "directory": Path("/my/files/are/here"),
        "media_type": "text/plain",
        "permissions": "-w-rw-r--",
        "size": 111_222_333,
        "created_at": datetime.now(tz=tz) - timedelta(days=14),
        "updated_at": datetime.now(tz=tz),
        "expiration_date": datetime.now(tz=UTC) + timedelta(days=366),
    }


def test_file_created(file_properties: dict[str, Any]) -> None:
    """Test that a file can be created correctly."""
    new_file = File(
        **file_properties,
    )
    for key, value in file_properties.items():
        assert getattr(new_file, key) == value, (
            f"{key} does not match: {getattr(new_file, key)} != {value}"
        )


def test_file_path(file_properties: dict[str, Any]) -> None:
    """Test that the path property returns the correct path."""
    new_file = File(
        **file_properties,
    )
    assert new_file.path == Path(file_properties["directory"]) / file_properties["name"]


def test_chmod_props(file_properties: dict[str, Any]) -> None:
    """Test that the chmod_props property returns the correct chmod properties."""
    new_file = File(
        **file_properties,
    )
    assert new_file.chmod_props == "264"  # 264 (octal) <=> '-w-rw-r--'
