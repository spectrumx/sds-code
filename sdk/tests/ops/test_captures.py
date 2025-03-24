"""Tests capture operations."""
# pylint: disable=redefined-outer-name

import json
import uuid as uuidlib
from pathlib import PurePosixPath
from typing import Any

import pytest
import responses
from loguru import logger as log
from pydantic import UUID4
from spectrumx import Client
from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.captures import CaptureType

from tests.conftest import get_captures_endpoint

log.trace("Placeholder log to avoid reimporting or resolving unused import warnings.")

# globally toggles dry run mode in case we want to run these under an integration mode.
DRY_RUN: bool = False


@pytest.fixture
def sample_capture_uuid() -> UUID4:
    """Returns a sample capture UUID for testing."""
    return uuidlib.uuid4()


@pytest.fixture
def sample_capture_data(sample_capture_uuid: UUID4) -> dict[str, Any]:
    """Returns sample capture data for testing."""
    return {
        "uuid": str(sample_capture_uuid),
        "capture_type": CaptureType.DigitalRF.value,
        "top_level_dir": "/test/capture/directory",
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {"sample": "props"},
        "files": [
            {
                "uuid": uuidlib.uuid4().hex,
                "name": "capture_file1.drf",
                "directory": "/test/capture/directory",
            },
            {
                "uuid": uuidlib.uuid4().hex,
                "name": "capture_file2.drf",
                "directory": "/test/capture/directory",
            },
        ],
    }


def test_create_capture(client: Client, responses: responses.RequestsMock) -> None:
    """Test creating a capture."""
    # ARRANGE
    client.dry_run = DRY_RUN
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    channel = "channel1"
    capture_uuid = uuidlib.uuid4()

    # Mock response
    mocked_capture_response = {
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(top_level_dir),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {},
        "channel": channel,
        "files": [],
    }

    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=201,
        json=mocked_capture_response,
    )

    # ACT
    capture = client.captures.create(
        top_level_dir=top_level_dir,
        capture_type=capture_type,
        channel=channel,
    )

    # ASSERT
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.top_level_dir == top_level_dir
    assert capture.channel == channel
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"
    assert responses.calls[0].request.url == get_captures_endpoint(client)


def test_create_capture_dry_run(client: Client) -> None:
    """Test creating a capture in dry run mode."""
    # ARRANGE
    client.dry_run = True
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF

    # ACT
    capture = client.captures.create(
        top_level_dir=top_level_dir,
        capture_type=capture_type,
    )

    # ASSERT
    assert capture.uuid is not None
    assert capture.capture_type == capture_type
    assert capture.top_level_dir == top_level_dir
    assert len(capture.files) == 0


def test_listing_captures(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
) -> None:
    """Test listing captures."""
    # ARRANGE
    client.dry_run = DRY_RUN
    mocked_listing_response = {"results": [sample_capture_data], "next": None}

    responses.add(
        method=responses.GET,
        url=get_captures_endpoint(client),
        status=200,
        json=mocked_listing_response,
    )

    # ACT
    captures = client.captures.listing()

    # ASSERT
    assert len(captures) == 1
    assert str(captures[0].uuid) == sample_capture_data["uuid"]
    assert captures[0].capture_type.value == sample_capture_data["capture_type"]
    assert len(captures[0].files) == len(sample_capture_data["files"])
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"


def test_listing_captures_with_type_filter(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
) -> None:
    """Test listing captures with type filter."""
    # ARRANGE
    client.dry_run = DRY_RUN
    capture_type = CaptureType.DigitalRF
    mocked_listing_response = {"results": [sample_capture_data], "next": None}

    # Build the URL with query parameter
    url = f"{get_captures_endpoint(client)}?capture_type={capture_type.value}"

    responses.add(
        method=responses.GET,
        url=url,
        status=200,
        json=mocked_listing_response,
    )

    # ACT
    captures = client.captures.listing(capture_type=capture_type)

    # ASSERT
    assert len(captures) == 1
    assert captures[0].capture_type == capture_type
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"
    assert responses.calls[0].request.url is not None, "Request URL should not be None"
    assert capture_type.value in responses.calls[0].request.url


def test_listing_captures_dry_run(client: Client) -> None:
    """Test listing captures in dry run mode."""
    # ARRANGE
    num_dry_run_captures = 3  # expected number of captures in a dry run listing
    client.dry_run = True
    capture_type = CaptureType.RadioHound

    # ACT
    captures = client.captures.listing(capture_type=capture_type)

    # ASSERT
    assert isinstance(captures, list)
    assert len(captures) == num_dry_run_captures
    for capture in captures:
        assert isinstance(capture, Capture)


def test_read_capture(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
    sample_capture_uuid: UUID4,
) -> None:
    """Test reading a capture."""
    # ARRANGE
    client.dry_run = DRY_RUN

    responses.add(
        method=responses.GET,
        url=get_captures_endpoint(client, capture_id=sample_capture_uuid.hex),
        status=200,
        body=json.dumps(sample_capture_data),
    )

    # ACT
    capture = client.captures.read(capture_uuid=sample_capture_uuid)

    # ASSERT
    assert capture.uuid == sample_capture_uuid
    assert capture.capture_type.value == sample_capture_data["capture_type"]
    assert len(capture.files) == len(sample_capture_data["files"])
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"
    assert responses.calls[0].request.url == get_captures_endpoint(
        client, capture_id=sample_capture_uuid.hex
    )


def test_update_capture(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
    sample_capture_uuid: UUID4,
) -> None:
    """Test updating a capture."""
    # ARRANGE
    client.dry_run = DRY_RUN

    responses.add(
        method=responses.PUT,
        url=get_captures_endpoint(client, capture_id=sample_capture_uuid.hex),
        status=200,
        body=json.dumps(sample_capture_data),
    )

    # ACT
    client.captures.update(capture_uuid=sample_capture_uuid)

    # ASSERT
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "PUT"
    assert responses.calls[0].request.url == get_captures_endpoint(
        client, capture_id=sample_capture_uuid.hex
    )


def test_update_capture_dry_run(client: Client, sample_capture_uuid: UUID4) -> None:
    """Test updating a capture in dry run mode."""
    # ARRANGE
    client.dry_run = True

    # ACT & ASSERT - should not raise an exception
    client.captures.update(capture_uuid=sample_capture_uuid)


def test_capture_string_representation(sample_capture_data: dict[str, Any]) -> None:
    """Test the string representation of a capture."""
    # ARRANGE
    capture = Capture.model_validate(sample_capture_data)

    # ACT
    capture_str = str(capture)
    capture_repr = repr(capture)

    # ASSERT
    assert f"Capture(uuid={capture.uuid}" in capture_str
    assert f"type={capture.capture_type}" in capture_str
    assert f"files={len(capture.files)}" in capture_str
    assert capture.__class__.__name__ in capture_repr
    assert str(capture.uuid) in capture_repr
