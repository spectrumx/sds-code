"""High-level usage tests for the SpectrumX client.

Find asset-specific tests in `./ops/`.
"""
# pylint: disable=redefined-outer-name

import uuid as uuidlib
from pathlib import Path
from pathlib import PurePosixPath

import pytest
from loguru import logger as log
from responses import RequestsMock
from spectrumx import Client
from spectrumx.errors import AuthError
from spectrumx.gateway import API_TARGET_VERSION

from tests.conftest import get_files_endpoint

# --------
# FIXTURES
# --------


@pytest.fixture
def responses_dry_run(responses: RequestsMock) -> RequestsMock:
    """Fixture to mock responses for dry run mode."""
    responses.assert_all_requests_are_fired = False
    return responses


def get_auth_endpoint(client: Client) -> str:
    """Returns the endpoint for the auth API, with trailing slash."""
    return client.base_url + f"/api/{API_TARGET_VERSION}/auth/"


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


# ----------------------
# TESTS FOR DRY-RUN MODE
# ----------------------
class DryModeAssertionError(AssertionError):
    """Raised in test when a request is made in dry run mode."""


def test_dry_run_setter(client: Client) -> None:
    """Makes sure setter works, preventing unintended changes."""
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
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/my/upload/location"),
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
