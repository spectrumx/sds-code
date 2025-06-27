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
    channels = ["channel1"]  # Use channels instead of channel
    capture_uuid = uuidlib.uuid4()

    # Mock response
    mocked_capture_response = {
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(top_level_dir),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {},
        "channels": channels,
        "channel": channels[0],  # Legacy field for backward compatibility
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
        channels=channels,  # Use channels instead of channel
    )

    # ASSERT
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.top_level_dir == top_level_dir
    assert capture.channels == channels  # Computed property
    assert capture.channel == json.dumps(channels)  # Raw field
    assert capture.primary_channel == channels[0]  # Computed property
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


def test_create_capture_with_legacy_channel_parameter(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Test that providing the legacy channel parameter works
    (converted to channels).
    """
    # ARRANGE
    client.dry_run = DRY_RUN
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    channel = "test_channel"
    capture_uuid = uuidlib.uuid4()

    # Mock response
    mocked_capture_response = {
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(top_level_dir),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {},
        "channel": json.dumps([channel]),  # JSON string in response
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
        channel=channel,  # Legacy parameter should work
    )

    # ASSERT
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.channels == [channel]  # Computed property
    assert capture.channel == json.dumps([channel])  # Raw field
    assert capture.primary_channel == channel  # Computed property
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"

    # Verify the request payload contains channels (converted from channel)
    request_body = json.loads(responses.calls[0].request.body)
    assert "channels" in request_body
    assert request_body["channels"] == [channel]  # Single channel converted to list
    assert "channel" not in request_body  # Legacy parameter should not be sent


def test_create_capture_with_channels_parameter(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Test that providing the channels parameter works."""
    # ARRANGE
    client.dry_run = DRY_RUN
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    channels = ["test_channel1", "test_channel2"]
    capture_uuid = uuidlib.uuid4()

    # Mock response
    mocked_capture_response = {
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(top_level_dir),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {},
        "channel": json.dumps(channels),  # JSON string in response
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
        channels=channels,  # New parameter
    )

    # ASSERT
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.channels == channels  # Computed property
    assert capture.channel == json.dumps(channels)  # Raw field
    assert capture.primary_channel == channels[0]  # Computed property
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"

    # Verify the request payload contains channels
    request_body = json.loads(responses.calls[0].request.body)
    assert "channels" in request_body
    assert request_body["channels"] == channels
    assert "channel" not in request_body  # Legacy parameter should not be sent


def test_create_capture_with_both_channel_and_channels_fails(client: Client) -> None:
    """Test that providing both channel and channels parameters fails."""
    # ARRANGE
    client.dry_run = DRY_RUN
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF

    # ACT & ASSERT - should raise ValueError for providing both parameters
    with pytest.raises(
        ValueError, match="Only one of channel or channels can be provided"
    ):
        client.captures.create(
            top_level_dir=top_level_dir,
            capture_type=capture_type,
            channel="test_channel",
            channels=["test_channel1", "test_channel2"],  # Both parameters should fail
        )


def test_create_capture_with_multiple_channels(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Test creating a capture with multiple channels."""
    # ARRANGE
    client.dry_run = DRY_RUN
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    channels = ["channel1", "channel2", "channel3"]
    capture_uuid = uuidlib.uuid4()

    # Mock response with channels_metadata
    mocked_capture_response = {
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(top_level_dir),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {"center_freq": 2000000000, "bandwidth": 20000000},
        "channel": json.dumps(channels),  # JSON string in response
        "channels_metadata": [
            {
                "channel_name": "channel1",
                "channel_props": {"center_freq": 2000000000, "bandwidth": 20000000},
            },
            {
                "channel_name": "channel2",
                "channel_props": {"center_freq": 2100000000, "bandwidth": 20000000},
            },
            {
                "channel_name": "channel3",
                "channel_props": {"center_freq": 2200000000, "bandwidth": 20000000},
            },
        ],
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
        channels=channels,
    )

    # ASSERT
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.top_level_dir == top_level_dir
    assert capture.channels == channels  # Computed property
    assert capture.channel == json.dumps(channels)  # Raw field
    assert capture.primary_channel == channels[0]  # Computed property
    assert capture.channels_metadata == mocked_capture_response["channels_metadata"]
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"
    assert responses.calls[0].request.url == get_captures_endpoint(client)

    # Verify the request payload contains channels
    request_body = json.loads(responses.calls[0].request.body)
    assert "channels" in request_body
    assert request_body["channels"] == channels
    assert "channel" not in request_body  # Legacy parameter should not be sent


def test_read_legacy_capture_with_channel_field(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_uuid: UUID4,
) -> None:
    """Test reading a legacy capture that only has the channel field."""
    # ARRANGE
    client.dry_run = DRY_RUN

    # Mock response with legacy channel field only
    legacy_capture_data = {
        "uuid": str(sample_capture_uuid),
        "capture_type": CaptureType.DigitalRF.value,
        "top_level_dir": "/test/capture/directory",
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {"center_freq": 2000000000},
        "channel": "legacy_channel",  # Legacy string format
        "files": [],
    }

    responses.add(
        method=responses.GET,
        url=get_captures_endpoint(client, capture_id=sample_capture_uuid.hex),
        status=200,
        body=json.dumps(legacy_capture_data),
    )

    # ACT
    capture = client.captures.read(capture_uuid=sample_capture_uuid)

    # ASSERT
    assert capture.uuid == sample_capture_uuid
    assert capture.capture_type.value == legacy_capture_data["capture_type"]
    assert capture.channel == "legacy_channel"  # Raw field preserved
    assert capture.channels == ["legacy_channel"]  # Computed property converts to list
    assert capture.primary_channel == "legacy_channel"  # Computed property
    assert len(capture.files) == len(legacy_capture_data["files"])
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"


def test_list_captures_with_legacy_channel_data(
    client: Client,
    responses: responses.RequestsMock,
) -> None:
    """Test listing captures that include legacy captures with only
    channel field.
    """
    # ARRANGE
    client.dry_run = DRY_RUN

    # Constants
    expected_capture_count = 2

    # Mock response with mixed legacy and new captures
    legacy_capture = {
        "uuid": str(uuidlib.uuid4()),
        "capture_type": CaptureType.DigitalRF.value,
        "top_level_dir": "/test/legacy/capture",
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {"center_freq": 2000000000},
        "channel": "legacy_channel",  # Legacy string format
        "files": [],
    }

    new_capture = {
        "uuid": str(uuidlib.uuid4()),
        "capture_type": CaptureType.DigitalRF.value,
        "top_level_dir": "/test/new/capture",
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {"center_freq": 2100000000},
        "channel": json.dumps(["new_channel1", "new_channel2"]),  # JSON format
        "files": [],
    }

    mocked_listing_response = {"results": [legacy_capture, new_capture], "next": None}

    responses.add(
        method=responses.GET,
        url=get_captures_endpoint(client),
        status=200,
        json=mocked_listing_response,
    )

    # ACT
    captures = client.captures.listing()

    # ASSERT
    assert len(captures) == expected_capture_count

    # Check legacy capture
    legacy_cap = captures[0]
    assert legacy_cap.channel == "legacy_channel"  # Raw field
    assert legacy_cap.channels == ["legacy_channel"]  # Computed property
    assert legacy_cap.primary_channel == "legacy_channel"  # Computed property

    # Check new capture
    new_cap = captures[1]
    assert new_cap.channel == json.dumps(["new_channel1", "new_channel2"])  # Raw field
    assert new_cap.channels == ["new_channel1", "new_channel2"]  # Computed property
    assert new_cap.primary_channel == "new_channel1"  # Computed property

    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "GET"


def test_upload_capture_with_multiple_channels(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Test uploading a capture with multiple channels."""
    # ARRANGE
    client.dry_run = DRY_RUN
    local_path = Path("/local/test/path")
    sds_path = PurePosixPath("/test/capture")
    capture_type = CaptureType.DigitalRF
    channels = ["channel1", "channel2"]
    capture_uuid = uuidlib.uuid4()

    # Mock file upload response
    mocked_file_response = {
        "uuid": str(uuidlib.uuid4()),
        "name": "test.h5",
        "directory": str(sds_path),
        "media_type": "application/octet-stream",
        "permissions": "private",
    }

    # Mock capture creation response
    mocked_capture_response = {
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(sds_path),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {"center_freq": 2000000000},
        "channel": json.dumps(channels),  # JSON string in response
        "channels_metadata": [
            {"channel_name": "channel1", "channel_props": {"center_freq": 2000000000}},
            {"channel_name": "channel2", "channel_props": {"center_freq": 2100000000}},
        ],
        "files": [mocked_file_response],
    }

    # Mock file listing response
    responses.add(
        method=responses.GET,
        url=get_files_endpoint(client),
        status=200,
        json={"results": [mocked_file_response], "count": 1},
    )

    # Mock capture creation response
    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=201,
        json=mocked_capture_response,
    )

    # ACT
    capture = client.upload_capture(
        local_path=local_path,
        sds_path=sds_path,
        capture_type=capture_type,
        channels=channels,
    )

    # ASSERT
    assert capture is not None
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.channels == channels  # Computed property
    assert capture.channel == json.dumps(channels)  # Raw field
    assert capture.channels_metadata == mocked_capture_response["channels_metadata"]
    assert capture.primary_channel == channels[0]  # Computed property

    # Verify the capture creation request contains channels
    capture_request = responses.calls[-1]  # Last call should be capture creation
    request_body = json.loads(capture_request.request.body)
    assert "channels" in request_body
    assert request_body["channels"] == channels
    assert "channel" not in request_body  # Legacy parameter should not be sent
