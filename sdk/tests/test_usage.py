"""
Tests for the high-level usage of SpectrumX client.
"""

# pylint: disable=redefined-outer-name
import uuid as uuidlib
from datetime import datetime
from pathlib import Path

import pytest
from loguru import logger as log
from responses import RequestsMock
from spectrumx import Client
from spectrumx.errors import AuthError
from spectrumx.gateway import API_TARGET_VERSION


# --------
# FIXTURES
# --------
@pytest.fixture
def client() -> Client:
    """Fixture to create a Client instance for testing."""
    return Client(host="sds.crc.nd.edu")


@pytest.fixture
def responses_dry_run(responses: RequestsMock) -> RequestsMock:
    """Fixture to mock responses for dry run mode."""
    responses.assert_all_requests_are_fired = False
    return responses


def get_auth_endpoint(client: Client) -> str:
    """Returns the endpoint for the auth API, with trailing slash."""
    return client.base_url + f"/api/{API_TARGET_VERSION}/auth/"


def get_files_endpoint(client: Client) -> str:
    """Returns the endpoint for the files API, with trailing slash."""
    return client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/"


# ------------------------
# TESTS FOR AUTHENTICATION
# ------------------------
def test_authentication_200_succeeds(client: Client, responses: RequestsMock) -> None:
    """Given a successful auth response, the client must be authenticated."""
    responses.get(
        get_auth_endpoint(client),
        body="{}",
        status=200,
        content_type="application/json",
    )
    # list registered URLs
    log.error(responses.calls)
    # disable the dry run mode for this,
    # since we're testing the actual request
    client.dry_run = False
    client.authenticate()
    assert client.is_authenticated


def test_authentication_401_fails(client: Client, responses: RequestsMock) -> None:
    """Given a failed auth response, the client must raise AuthError."""
    responses.get(
        get_auth_endpoint(client),
        body="{}",
        status=401,
        content_type="application/json",
    )
    client.dry_run = False  # to test the actual request
    with pytest.raises(AuthError):
        client.authenticate()


# -------------------------
# TESTS FOR FILE OPERATIONS
# -------------------------
def test_get_file_by_id(client: Client, responses: RequestsMock) -> None:
    """Given a file ID, the client must return the file."""
    uuid = uuidlib.uuid4()
    url: str = get_files_endpoint(client) + f"{uuid.hex}/"
    responses.get(
        url=url,
        status=200,
        json={
            "created_at": "2021-10-01T12:00:00Z",
            "directory": "/my/files/are/here/",
            "expiration_date": "2021-10-01T12:12:00Z",
            "media_type": "text/plain",
            "name": "file.txt",
            "permissions": "rw-rw-r--",
            "size": 321,
            "updated_at": "2021-10-01T12:00:00Z",
            "uuid": uuid.hex,
        },
    )
    client.dry_run = False  # to test the actual request
    file_sample = client.get_file(file_uuid=uuid.hex)
    assert file_sample.uuid == uuid


def test_file_get_returns_valid(
    client: Client,
) -> None:
    """The get_file method must return a valid File instance.

    Note the file may not exist locally, but the File instance can still be valid.
        That is the case for dry-runs - which use sample files - and for files fetched
        from the server that have not yet been downloaded.
    """

    file_id = uuidlib.uuid4()
    file_size = 888
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    file_sample = client.get_file(file_uuid=file_id.hex)
    assert file_sample.is_sample is True, "The file must be a sample file"  # pyright: ignore[reportPrivateUsage]
    assert file_sample.uuid is not None
    assert file_sample.name.startswith("dry-run-")
    assert file_sample.media_type == "text/plain"
    assert file_sample.size == file_size
    assert file_sample.directory == Path("./sds-files/dry-run/")
    assert file_sample.permissions == "rw-rw-r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert isinstance(
        file_sample.expiration_date, datetime
    ), "Expiration date should be a datetime"
    assert file_sample.expiration_date > file_sample.created_at


def test_file_upload(client: Client, temp_file_with_text_contents: Path) -> None:
    """The upload_file method must return a valid File instance."""
    test_file_size = temp_file_with_text_contents.stat().st_size
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    file_sample = client.upload_file(
        file_path=temp_file_with_text_contents,
        sds_path=Path("/my/upload/location"),
    )
    assert (
        file_sample.is_sample is False
    ), "The file must be a real file on disk (not a sample), even for this test"  # pyright: ignore[reportPrivateUsage]
    assert (
        temp_file_with_text_contents == file_sample.local_path
    ), "Local path does not match"
    assert file_sample.uuid is None, "A local file must not have a UUID"
    assert file_sample.name is not None, "Expected a file name"
    assert file_sample.media_type == "text/plain", "Expected media type 'text/plain'"
    assert file_sample.size == test_file_size, "Expected the test file to be 4030 bytes"
    assert "/tmp/pytest-" in str(  # noqa: S108
        file_sample.local_path
    ), "Expected the temp file directory"
    assert file_sample.directory == Path("/my/upload/location")
    assert file_sample.permissions == "rw-r--r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert (
        file_sample.expiration_date is None
    ), "Local files should not have an expiration date"


# ----------------------
# TESTS FOR DRY-RUN MODE
# ----------------------
class DryModeAssertionError(AssertionError):
    """Raised in test when a request is made in dry run mode."""


def test_dry_run_setter(client: Client, responses_dry_run: RequestsMock) -> None:
    """Makes sure setter works.

    NOTE: Test behavior of this setter might differ from actual \
        one in early releases. See notes in the setter code.
    """
    client.dry_run = False
    assert client.dry_run is False, "Dry-run setter failed."
    client.dry_run = True
    assert client.dry_run is True, "Dry-run setter failed."


def test_dry_run_enabled_by_default(client: Client) -> None:
    """Dry-run mode must be enabled by default."""
    assert client.dry_run is True, "Dry-run must be enabled by default."


def test_dry_auth_does_not_request(
    client: Client, responses_dry_run: RequestsMock
) -> None:
    """When in dry mode, the client must not make any requests."""
    responses_dry_run.add_callback(
        responses_dry_run.GET,
        url=get_auth_endpoint(client),
        callback=lambda _: DryModeAssertionError(
            "No requests must be made in dry run mode"
        ),
    )
    client.dry_run = True
    assert client.dry_run is True, "Dry-run setter failed."
    client.authenticate()


def test_dry_file_upload_does_not_request(
    client: Client, responses_dry_run: RequestsMock, temp_file_with_text_contents: Path
) -> None:
    """When in dry run mode, the upload method must not make any requests."""
    responses_dry_run.add_callback(
        responses_dry_run.POST,
        url=get_files_endpoint(client),
        callback=lambda _: DryModeAssertionError(
            "No requests must be made in dry run mode"
        ),
    )
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    _file_sample = client.upload_file(
        file_path=temp_file_with_text_contents,
        sds_path=Path("/my/upload/location"),
    )


def test_dry_file_get_does_not_request(
    client: Client, responses_dry_run: RequestsMock
) -> None:
    """When in dry run mode, the get_file method must not make any requests."""

    file_id = uuidlib.uuid4()

    responses_dry_run.add_callback(
        responses_dry_run.GET,
        url=get_files_endpoint(client) + f"{file_id.hex}/",
        callback=lambda _: DryModeAssertionError(
            "No requests must be made in dry run mode"
        ),
    )

    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    _file_sample = client.get_file(file_uuid=file_id.hex)
