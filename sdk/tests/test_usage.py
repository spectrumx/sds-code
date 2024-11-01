"""
Tests for the high-level usage of SpectrumX client.
"""

# pylint: disable=redefined-outer-name
import uuid as uuidlib
from datetime import date
from datetime import datetime
from pathlib import Path

import pytest
from responses import RequestsMock
from spectrumx import Client
from spectrumx.errors import AuthError
from spectrumx.gateway import Endpoints


@pytest.fixture
def client() -> Client:
    """Fixture to create a Client instance for testing."""
    return Client(host="sds.crc.nd.edu")


class DryModeAssertionError(AssertionError):
    """Raised in test when a request is made in dry run mode."""


@pytest.fixture
def responses_dry_run(responses: RequestsMock) -> RequestsMock:
    """Fixture to mock responses for dry run mode."""
    responses.assert_all_requests_are_fired = False
    return responses


def test_authentication_200_succeeds(client: Client, responses: RequestsMock) -> None:
    """Given a successful auth response, the client must be authenticated."""
    responses.get(
        client.base_url + "/auth",
        body="{}",
        status=200,
        content_type="application/json",
    )
    client.authenticate()
    assert client.is_authenticated


def test_authentication_401_fails(client: Client, responses: RequestsMock) -> None:
    """Given a failed auth response, the client must raise AuthError."""
    responses.get(
        client.base_url + "/auth",
        body="{}",
        status=401,
        content_type="application/json",
    )
    with pytest.raises(AuthError):
        client.authenticate()


def test_get_file_by_id(client: Client, responses: RequestsMock) -> None:
    """Given a file ID, the client must return the file."""
    uuid = uuidlib.uuid4()
    url: str = client.base_url + Endpoints.FILES + f"/{uuid.hex}"
    responses.get(
        url=url,
        status=200,
        json={
            "created_at": "2021-10-01T12:00:00",
            "directory": "/my/files/are/here/",
            "expiration_date": "2021-10-01",
            "media_type": "text/plain",
            "name": "file.txt",
            "permissions": "rw-rw-r--",
            "size": 321,
            "updated_at": "2021-10-01T12:00:00",
            "uuid": uuid.hex,
        },
    )
    file_sample = client.get_file(file_uuid=uuid.hex)
    assert file_sample.uuid == uuid


def test_dry_run_enabled(client: Client, responses_dry_run: RequestsMock) -> None:
    """When in dry mode, the client must not make any requests."""
    responses_dry_run.add_callback(
        responses_dry_run.GET,
        url=client.base_url + "/auth",
        callback=lambda _: DryModeAssertionError(
            "No requests must be made in dry run mode"
        ),
    )
    assert client.dry_run is False, "Dry run must be disabled"
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled when testing."
    client.authenticate()


def test_dry_run_get_file(client: Client, responses_dry_run: RequestsMock) -> None:
    """When in dry run mode, the client must return a predetermined sample file."""

    file_id = uuidlib.uuid4()

    responses_dry_run.add_callback(
        responses_dry_run.GET,
        url=client.base_url + Endpoints.FILES + f"/{file_id.hex}",
        callback=lambda _: DryModeAssertionError(
            "No requests must be made in dry run mode"
        ),
    )

    file_size = 888
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled when testing."
    file_sample = client.get_file(file_uuid=file_id.hex)
    assert file_sample.is_sample is True, "The file must be a sample file"  # pyright: ignore[reportPrivateUsage]
    assert file_sample.uuid is not None
    assert file_sample.name == "dry-run-file.txt"
    assert file_sample.media_type == "text/plain"
    assert file_sample.size == file_size
    assert file_sample.directory == Path("./sds-files/dry-run/")
    assert file_sample.permissions == "rw-rw-r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert isinstance(file_sample.expiration_date, date)
    assert file_sample.expiration_date > file_sample.created_at.date()


def test_dry_run_upload_file(
    client: Client, responses_dry_run: RequestsMock, temp_file_with_text_contents: Path
) -> None:
    """When in dry run mode, the client must return a predetermined sample file."""
    responses_dry_run.add_callback(
        responses_dry_run.POST,
        url=client.base_url + Endpoints.FILES,
        callback=lambda _: DryModeAssertionError(
            "No requests must be made in dry run mode"
        ),
    )
    test_file_size = temp_file_with_text_contents.stat().st_size
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled when testing."
    file_sample = client.upload_file(
        file_path=temp_file_with_text_contents,
        sds_path=Path("/my/upload/location"),
    )
    assert (
        file_sample.is_sample is False
    ), "The file must be a real file on disk, even when testing"  # pyright: ignore[reportPrivateUsage]
    assert (
        temp_file_with_text_contents == file_sample.local_path
    ), "Local path does not match"
    assert file_sample.uuid is None, "A local file must not have a UUID"
    assert file_sample.name is not None
    assert file_sample.media_type == "text/plain", "Expected media type 'text/plain'"
    assert file_sample.size == test_file_size, "Expected the test file to be 4030 bytes"
    assert "/tmp/pytest-" in str(  # noqa: S108
        file_sample.local_path
    ), "Expected the temp file directory"
    assert str(file_sample.directory) == "/my/upload/location"
    assert file_sample.permissions == "rw-r--r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert (
        file_sample.expiration_date is None
    ), "Local files should not have an expiration date"
