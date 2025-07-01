"""Tests capture operations."""
# pylint: disable=redefined-outer-name

import json
import uuid as uuidlib
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import pytest
import responses
from loguru import logger as log
from pydantic import UUID4
from spectrumx import Client
from spectrumx.errors import SDSError
from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.captures import CaptureType

from tests.conftest import get_captures_endpoint
from tests.conftest import get_content_check_endpoint
from tests.conftest import get_files_endpoint

log.trace("Placeholder log to avoid reimporting or resolving unused import warnings.")

# globally toggles dry run mode in case we want to run these under an integration mode.
DRY_RUN: bool = False

MULTICHANNEL_EXPECTED_COUNT = 2


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


def add_file_upload_mock(
    client: Client,
    responses: responses.RequestsMock,
    directory: str = "/test/multichannel",
) -> None:
    responses.add(
        method=responses.POST,
        url=get_files_endpoint(client),
        status=201,
        json={
            "uuid": str(uuidlib.uuid4()),
            "name": "test.txt",
            "directory": directory,
            "size": 123,
            "is_deleted": False,
            "created_at": "2024-01-01T00:00:00Z",
            "updated_at": "2024-01-01T00:00:00Z",
            "expiration_date": None,
            "media_type": "application/octet-stream",
            "permissions": "rwxr--r--",
            "owner": {"id": 1, "email": "test@example.com", "name": "Test User"},
        },
    )


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
    assert isinstance(capture.created_at, datetime), (
        "Expected created_at to be a datetime object"
    )
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


def test_upload_capture_dry_run(client: Client, tmp_path: Path) -> None:
    """Test uploading capture in dry run mode."""
    # ARRANGE
    client.dry_run = True

    test_dir = tmp_path / "test_capture_dry"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("capture upload - dry run test")

    capture_type = CaptureType.DigitalRF

    # ACT
    capture = client.upload_capture(
        local_path=test_dir,
        sds_path="/test/capture/dry-run",
        capture_type=capture_type,
    )

    # ASSERT
    assert capture is not None
    assert capture.uuid is not None
    assert capture.capture_type == capture_type
    assert len(capture.files) == 0  # Dry run simulates empty files list


def test_upload_capture_upload_fails(
    client: Client, responses: responses.RequestsMock, tmp_path: Path
) -> None:
    """Test handling when file upload fails."""
    # ARRANGE
    client.dry_run = DRY_RUN

    test_dir = tmp_path / "test_capture_fail"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("capture upload - fail test")

    # mock upload to fail with 500 error
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=500,
        json={"error": "Server error"},
    )

    # ACT & ASSERT
    with pytest.raises(SDSError):
        client.upload_capture(
            local_path=test_dir,
            sds_path="/test/capture/fail",
            capture_type=CaptureType.DigitalRF,
            raise_on_error=True,
        )

    # Test with raise_on_error=False
    result = client.upload_capture(
        local_path=test_dir,
        sds_path="/test/capture/fail",
        capture_type=CaptureType.DigitalRF,
        raise_on_error=False,
        verbose=False,
    )

    assert result is None


def test_upload_capture_no_files(client: Client, tmp_path: Path) -> None:
    """Test upload capture with an empty directory."""
    # ARRANGE
    client.dry_run = DRY_RUN

    # Create empty directory
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    # ACT
    result = client.upload_capture(
        local_path=empty_dir,
        sds_path="/test/capture/empty",
        capture_type=CaptureType.DigitalRF,
        verbose=False,
    )

    # ASSERT
    assert result is None


def test_upload_multichannel_drf_capture_dry_run(
    client: Client, tmp_path: Path
) -> None:
    """Test uploading multi-channel DRF capture in dry run mode."""
    # ARRANGE
    client.dry_run = True
    test_dir = tmp_path / "test_multichannel_drf"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("multi-channel capture upload - dry run test")

    channels = ["channel1", "channel2", "channel3"]

    # ACT
    captures = client.upload_multichannel_drf_capture(
        local_path=test_dir,
        sds_path="/test/multichannel/dry-run",
        channels=channels,
    )

    # ASSERT
    assert captures is not None
    assert len(captures) == len(channels)
    for i, capture in enumerate(captures):
        assert capture.uuid is not None
        assert capture.capture_type == CaptureType.DigitalRF
        assert capture.channel == channels[i]
        assert len(capture.files) == 0  # Dry run simulates empty files list


def test_upload_multichannel_drf_capture_success(
    client: Client, responses: responses.RequestsMock, tmp_path: Path
) -> None:
    """Test successful multi-channel DRF capture upload."""
    # ARRANGE
    client.dry_run = DRY_RUN
    test_dir = tmp_path / "test_multichannel_drf"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("multi-channel capture upload test")

    channels = ["channel1", "channel2"]
    capture_uuids = [uuidlib.uuid4(), uuidlib.uuid4()]

    # Mock file content check endpoint
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=200,
        json={
            "file_contents_exist_for_user": False,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": False,
        },
    )

    # Mock capture creation endpoints
    for _, (channel, uuid) in enumerate(zip(channels, capture_uuids, strict=False)):
        mocked_response = {
            "uuid": uuid.hex,
            "capture_type": CaptureType.DigitalRF.value,
            "top_level_dir": "/test/multichannel",
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
            json=mocked_response,
        )

    add_file_upload_mock(client, responses)

    # ACT
    captures = client.upload_multichannel_drf_capture(
        local_path=test_dir,
        sds_path="/test/multichannel",
        channels=channels,
    )

    # ASSERT
    assert captures is not None
    assert len(captures) == MULTICHANNEL_EXPECTED_COUNT
    for i, capture in enumerate(captures):
        assert capture.uuid == capture_uuids[i]
        assert capture.capture_type == CaptureType.DigitalRF
        assert capture.channel == channels[i]


def test_upload_multichannel_drf_capture_existing_capture(
    client: Client, responses: responses.RequestsMock, tmp_path: Path
) -> None:
    """Test multi-channel DRF capture when one capture already exists."""
    # ARRANGE
    client.dry_run = DRY_RUN
    test_dir = tmp_path / "test_multichannel_drf"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("multi-channel capture upload test")

    channels = ["channel1", "channel2"]
    existing_uuid = uuidlib.uuid4()
    new_uuid = uuidlib.uuid4()

    # Mock upload endpoint with correct response structure
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=200,
        json={
            "file_contents_exist_for_user": False,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": False,
        },
    )

    # Mock capture creation endpoint that fails with existing capture error
    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=400,
        json={
            "detail": (
                "One or more capture creation constraints violated:\n"
                "\tdrf_unique_channel_and_tld: This channel and top level directory "
                f"are already in use by another capture: {existing_uuid.hex}"
            )
        },
    )

    # Mock capture read endpoint for existing capture
    responses.add(
        method=responses.GET,
        url=get_captures_endpoint(client, capture_id=existing_uuid.hex),
        status=200,
        json={
            "uuid": str(existing_uuid),
            "top_level_dir": "/test/multichannel",
            "capture_type": CaptureType.DigitalRF.value,
            "channel": "channel1",
            "files": [],
            "capture_props": {},
            "index_name": "test_index",
            "origin": CaptureOrigin.User.value,
        },
    )

    # Mock second capture creation endpoint
    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=201,
        json={
            "uuid": str(new_uuid),
            "top_level_dir": "/test/multichannel",
            "capture_type": CaptureType.DigitalRF.value,
            "channel": "channel2",
            "files": [],
            "capture_props": {},
            "index_name": "test_index",
            "origin": CaptureOrigin.User.value,
        },
    )

    add_file_upload_mock(client, responses)

    # ACT
    captures = client.upload_multichannel_drf_capture(
        local_path=test_dir,
        sds_path="/test/multichannel",
        channels=channels,
    )

    # ASSERT
    assert captures is not None
    assert len(captures) == MULTICHANNEL_EXPECTED_COUNT
    assert captures[0].uuid == existing_uuid
    assert captures[1].uuid == new_uuid


def test_upload_multichannel_drf_capture_creation_fails(
    client: Client, responses: responses.RequestsMock, tmp_path: Path
) -> None:
    """Test multi-channel DRF capture when capture creation fails for other reasons."""
    # ARRANGE
    client.dry_run = DRY_RUN
    test_dir = tmp_path / "test_multichannel_drf"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("multi-channel capture upload test")

    channels = ["channel1", "channel2"]
    first_uuid = uuidlib.uuid4()

    # Mock upload endpoint with correct response structure
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=200,
        json={
            "file_contents_exist_for_user": False,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": False,
        },
    )

    # Mock first capture creation (success)
    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=201,
        json={
            "uuid": first_uuid.hex,
            "capture_type": CaptureType.DigitalRF.value,
            "top_level_dir": "/test/multichannel",
            "channel": channels[0],
            "files": [],
            "capture_props": {},
            "index_name": "test_index",
            "origin": CaptureOrigin.User.value,
        },
    )

    # Mock second capture creation (fails with different error)
    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=400,
        json={"error": "Some other error that's not about existing captures"},
    )

    # Mock deletion of first capture
    responses.add(
        method=responses.DELETE,
        url=get_captures_endpoint(client, capture_id=first_uuid.hex),
        status=204,
    )

    add_file_upload_mock(client, responses)

    # ACT
    result = client.upload_multichannel_drf_capture(
        local_path=test_dir,
        sds_path="/test/multichannel",
        channels=channels,
        raise_on_error=False,
    )

    # ASSERT
    assert result == []


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


def test_delete_capture(client: Client, responses: responses.RequestsMock) -> None:
    """Test deleting a capture."""
    # ARRANGE
    client.dry_run = DRY_RUN
    capture_uuid = uuidlib.uuid4()

    # Mock response
    responses.add(
        method=responses.DELETE,
        url=get_captures_endpoint(client, capture_id=capture_uuid.hex),
        status=204,
    )

    # ACT
    result = client.captures.delete(capture_uuid=capture_uuid)

    # ASSERT
    assert result is True
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "DELETE"
    assert responses.calls[0].request.url == get_captures_endpoint(
        client, capture_id=capture_uuid.hex
    )


def test_delete_capture_dry_run(client: Client) -> None:
    """Test deleting a capture in dry run mode."""
    # ARRANGE
    client.dry_run = True
    capture_uuid = uuidlib.uuid4()

    # ACT
    result = client.captures.delete(capture_uuid=capture_uuid)

    # ASSERT
    assert result is True  # Dry run should simulate success


def test_search_captures_freq_range(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
) -> None:
    """Test searching captures with a frequency range query."""
    # ARRANGE
    client.dry_run = DRY_RUN

    search_response = {
        "results": [sample_capture_data],
        "next": None,
        "previous": None,
        "count": 1,
    }
    field_path = "capture_props.center_freq"
    query_type = "range"
    filter_value = {"gte": 1990000000, "lte": 2010000000}
    search_endpoint = get_captures_endpoint(client)

    responses.add(
        method=responses.GET,
        url=search_endpoint,
        status=200,
        json=search_response,
    )

    # ACT
    captures = client.captures.advanced_search(
        field_path=field_path,
        query_type=query_type,
        filter_value=filter_value,
    )

    # ASSERT
    assert len(captures) == 1
    assert str(captures[0].uuid) == sample_capture_data["uuid"]
    assert captures[0].capture_type.value == sample_capture_data["capture_type"]
    assert len(captures[0].files) == len(sample_capture_data["files"])
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"


def test_search_captures_dry_run(client: Client) -> None:
    """Test searching captures in dry run mode."""
    # ARRANGE
    client.dry_run = True

    field_path = "capture_props.center_freq"
    query_type = "range"
    filter_value = {"gte": 1990000000, "lte": 2010000000}

    # ACT
    captures = client.captures.advanced_search(
        field_path=field_path,
        query_type=query_type,
        filter_value=filter_value,
    )

    # ASSERT
    num_dry_run_captures_for_search = 5
    assert isinstance(captures, list)
    assert len(captures) == num_dry_run_captures_for_search
    for capture in captures:
        assert isinstance(capture, Capture)
        assert capture.uuid is not None
        assert hasattr(capture, "capture_type")


def test_search_captures_exact_match(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
) -> None:
    """Test searching captures with an exact match query."""
    # ARRANGE
    client.dry_run = DRY_RUN

    search_response = {
        "results": [sample_capture_data],
        "next": None,
        "previous": None,
        "count": 1,
    }
    field_path = "capture_props.channel"
    query_type = "term"
    filter_value = {"value": "channel1"}
    search_endpoint = get_captures_endpoint(client)

    responses.add(
        method=responses.GET,
        url=search_endpoint,
        status=200,
        json=search_response,
    )

    # ACT
    matched_caps = client.captures.advanced_search(
        field_path=field_path,
        query_type=query_type,
        filter_value=filter_value,
    )

    # ASSERT
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"
    assert len(matched_caps) == 1
    capture = matched_caps[0]
    assert str(capture.uuid) == sample_capture_data["uuid"]
    assert capture.capture_type.value == sample_capture_data["capture_type"]
