"""Tests for the File model."""

# pylint: disable=redefined-outer-name

from datetime import datetime
from datetime import timedelta
from pathlib import PurePosixPath
from typing import Any

import pytest
from pydantic import BaseModel
from pytz import UTC
from pytz import timezone
from spectrumx.models.files import File
from spectrumx.models.files import PermissionRepresentation
from spectrumx.models.files import UnixPermissionStr


@pytest.fixture
def file_properties() -> dict[str, Any]:
    """Fixture to create a dictionary of file properties."""
    tz = timezone("UTC")
    return {
        "name": "test_file",
        "directory": PurePosixPath("/my/files/are/here"),
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
    assert new_file.path == file_properties["directory"] / file_properties["name"]


def test_chmod_props(file_properties: dict[str, Any]) -> None:
    """Test that the chmod_props property returns the correct chmod properties."""
    new_file = File(
        **file_properties,
    )
    assert new_file.chmod_props == "0o264"  # 264 (octal) <=> '-w-rw-r--'


# Permission Struct
def test_permission_deserialization() -> None:
    class Model(BaseModel):
        permission: UnixPermissionStr

    a = Model(permission="rwx------")
    assert a.permission == "rwx------"

    b = Model(permission=0o755)
    assert b.permission == "rwxr-xr-x"


def test_permission_serialization() -> None:
    class Model(BaseModel):
        permission: UnixPermissionStr

    a = Model(permission="rwx------")
    assert a.model_dump(context={"mode": "string"}) == {"permission": "rwx------"}

    assert a.model_dump(context={"mode": PermissionRepresentation.STRING}) == {
        "permission": "rwx------"
    }

    assert a.model_dump(context={"mode": "octal"}) == {"permission": "0o700"}

    assert a.model_dump(context={"mode": PermissionRepresentation.OCTAL}) == {
        "permission": "0o700"
    }

    b = Model(permission=0o755)
    assert b.model_dump(context={"mode": "string"}) == {"permission": "rwxr-xr-x"}

    assert b.model_dump(context={"mode": PermissionRepresentation.STRING}) == {
        "permission": "rwxr-xr-x"
    }

    assert b.model_dump(context={"mode": "octal"}) == {"permission": "0o755"}

    assert b.model_dump(context={"mode": PermissionRepresentation.OCTAL}) == {
        "permission": "0o755"
    }
