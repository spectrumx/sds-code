"""Tests capture operations."""
# pylint: disable=redefined-outer-name

from __future__ import annotations

import io
import json
import uuid as uuidlib
from datetime import UTC
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Any
from typing import cast
from urllib.parse import parse_qs
from uuid import uuid4

import pytest
from loguru import logger as log
from loguru import logger as loguru_logger
from spectrumx.api.captures import CaptureAPI
from spectrumx.api.captures import _extract_page_from_payload as extract
from spectrumx.errors import CaptureError
from spectrumx.errors import SDSError
from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.captures import CaptureType

from tests.conftest import get_capture_detach_from_datasets_url
from tests.conftest import get_capture_revoke_share_permissions_url
from tests.conftest import get_captures_endpoint
from tests.conftest import get_content_check_endpoint
from tests.conftest import get_files_endpoint

if TYPE_CHECKING:
    from collections.abc import Generator

    import responses
    from pydantic import UUID4
    from spectrumx import Client
    from spectrumx.gateway import GatewayClient

MULTICHANNEL_EXPECTED_COUNT: int = 2  # expected num of captures in multi-channel tests


@pytest.fixture
def dry_run() -> bool:
    """Default dry_run mode for capture tests (can be overridden per-test)."""
    return False


@pytest.fixture
def test_state_persistence() -> bool:
    """Whether to persist upload state in tests."""
    return False


@pytest.fixture
def loguru_caplog() -> Generator[io.StringIO]:
    """Capture loguru log messages into a StringIO buffer for assertions."""
    output = io.StringIO()
    handler_id = loguru_logger.add(
        output,
        format="{message}",
        level="DEBUG",
    )
    try:
        yield output
    finally:
        loguru_logger.remove(handler_id)


def _gateway_capture_sharing_fields() -> dict[str, Any]:
    """Owner and sharing fields the gateway includes on capture payloads."""
    return {
        "owner": {"id": 1, "email": "test@example.com", "name": "Test User"},
        "is_shared": False,
        "share_permissions": [],
        "datasets": [],
    }


@pytest.fixture
def sample_capture_uuid() -> UUID4:
    """Returns a sample capture UUID for testing."""
    return uuidlib.uuid4()


@pytest.fixture
def sample_capture_data(sample_capture_uuid: UUID4) -> dict[str, Any]:
    """Returns sample capture data for testing."""
    return {
        **_gateway_capture_sharing_fields(),
        "capture_props": {"sample": "props"},
        "capture_type": CaptureType.DigitalRF.value,
        "created_at": datetime.now(UTC).isoformat(),
        "index_name": "captures-drf",
        "name": "pytest-sample",
        "origin": CaptureOrigin.User.value,
        "top_level_dir": "/test/capture/directory",
        "uuid": str(sample_capture_uuid),
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


def _build_drf_capture_payload(**overrides: object) -> dict[str, object]:
    """Creates a DRF capture payload similar to what the gateway returns."""
    base_payload: dict[str, object] = {
        **_gateway_capture_sharing_fields(),
        "capture_props": {"sample_rate": 1.0},
        "capture_type": CaptureType.DigitalRF.value,
        "channel": "channel-0",
        "created_at": datetime.now(UTC).isoformat(),
        "index_name": "captures-drf",
        "name": "pytest-sample",
        "origin": CaptureOrigin.User.value,
        "top_level_dir": "/captures/sample",
        "uuid": str(uuid4()),
        "files": [
            {
                "uuid": str(uuid4()),
                "name": "sample.dat",
                "directory": "/captures/sample",
            }
        ],
    }
    base_payload.update(overrides)
    return base_payload


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


def test_create_capture(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """Test creating a capture."""
    # ARRANGE
    client.dry_run = dry_run
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    channel = "channel1"
    capture_uuid = uuidlib.uuid4()

    # Mock response
    mocked_capture_response = {
        **_gateway_capture_sharing_fields(),
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
    dry_run: bool,
) -> None:
    """Test listing captures."""
    # ARRANGE
    client.dry_run = dry_run
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
    dry_run: bool,
) -> None:
    """Test listing captures with type filter."""
    # ARRANGE
    client.dry_run = dry_run
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


def test_listing_skips_invalid_capture(loguru_caplog: io.StringIO) -> None:
    """Listing must ignore captures that fail validation."""
    valid_payload = _build_drf_capture_payload(name="valid")
    invalid_payload = _build_drf_capture_payload(name="invalid")
    invalid_payload.pop("capture_type")
    gateway = _GatewayStub(payload={"results": [valid_payload, invalid_payload]})
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = list(api.listing())

    assert len(captures) == 1
    assert captures[0].name == "valid"
    # The invalid capture was skipped — confirmed by state. The skip-warning path
    # (loguru, via log_user_warning) emitted a record; assert it ran via loguru capture
    # rather than stdlib caplog (the set-level-after-act form was a false-pass risk).
    assert loguru_caplog.getvalue(), "expected a validation-skip warning record"


def test_listing_defaults_missing_optional_fields() -> None:
    """Listing must tolerate missing optional fields by defaulting them."""
    payload_without_optional = _build_drf_capture_payload()
    payload_without_optional.pop("capture_props")
    payload_without_optional.pop("files")
    gateway = _GatewayStub(payload={"results": [payload_without_optional]})
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = api.listing()

    assert len(captures) == 1
    capture = captures[0]
    assert capture.capture_props == {}
    assert capture.files == []


def test_listing_tolerates_missing_owner() -> None:
    """Listing must not crash when owner field is absent from the payload."""
    payload_without_owner = _build_drf_capture_payload()
    payload_without_owner.pop("owner")
    gateway = _GatewayStub(payload={"results": [payload_without_owner]})
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = api.listing()

    assert len(captures) == 1
    assert captures[0].owner is None


def test_listing_tolerates_null_owner() -> None:
    """Listing must not crash when owner is null in the payload."""
    payload_null_owner = _build_drf_capture_payload(owner=None)
    gateway = _GatewayStub(payload={"results": [payload_null_owner]})
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = api.listing()

    assert len(captures) == 1
    assert captures[0].owner is None


def test_listing_tolerates_partial_owner() -> None:
    """Listing must not crash when owner has missing name/email fields."""
    payload_partial_owner = _build_drf_capture_payload(
        owner={"id": 1},
    )
    gateway = _GatewayStub(payload={"results": [payload_partial_owner]})
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = api.listing()

    assert len(captures) == 1
    assert captures[0].owner is not None
    assert captures[0].owner.name is None
    assert captures[0].owner.email is None


def test_read_capture(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
    sample_capture_uuid: UUID4,
    dry_run: bool,
) -> None:
    """Test reading a capture."""
    # ARRANGE
    client.dry_run = dry_run

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
    dry_run: bool,
) -> None:
    """Test updating a capture."""
    # ARRANGE
    client.dry_run = dry_run

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


def test_upload_capture_dry_run(
    client: Client, tmp_path: Path, test_state_persistence: bool
) -> None:
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
        capture_type=capture_type,
        local_path=test_dir,
        persist_state=test_state_persistence,
        sds_path="/test/capture/dry-run",
    )

    # ASSERT
    assert capture is not None
    assert capture.uuid is not None
    assert capture.capture_type == capture_type
    assert len(capture.files) == 0  # Dry run simulates empty files list


def test_upload_capture_upload_fails_raises(
    client: Client,
    responses: responses.RequestsMock,
    tmp_path: Path,
    dry_run: bool,
    test_state_persistence: bool,
) -> None:
    """Test raise_on_error=True raises SDSError when upload fails."""
    # ARRANGE
    client.dry_run = dry_run

    test_dir = tmp_path / "test_capture_fail_raises"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("capture upload - raises test")

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=500,
        json={"error": "Server error"},
    )

    # ACT & ASSERT
    with pytest.raises(SDSError):
        client.upload_capture(
            capture_type=CaptureType.DigitalRF,
            local_path=test_dir,
            persist_state=test_state_persistence,
            raise_on_error=True,
            sds_path="/test/capture/fail",
        )


def test_upload_capture_upload_fails_returns_none(
    client: Client,
    responses: responses.RequestsMock,
    tmp_path: Path,
    dry_run: bool,
    test_state_persistence: bool,
) -> None:
    """Test raise_on_error=False returns None when upload fails."""
    # ARRANGE
    client.dry_run = dry_run

    test_dir = tmp_path / "test_capture_fail_none"
    test_dir.mkdir()
    test_file = test_dir / "test.txt"
    test_file.write_text("capture upload - returns none test")

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=500,
        json={"error": "Server error"},
    )

    # ACT
    result = client.upload_capture(
        local_path=test_dir,
        sds_path="/test/capture/fail",
        capture_type=CaptureType.DigitalRF,
        persist_state=test_state_persistence,
        raise_on_error=False,
        verbose=False,
    )

    # ASSERT
    assert result is None


def test_upload_capture_no_files(
    client: Client, tmp_path: Path, dry_run: bool, test_state_persistence: bool
) -> None:
    """Test upload capture with an empty directory."""
    # ARRANGE
    client.dry_run = dry_run

    # Create empty directory
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()

    # ACT
    result = client.upload_capture(
        local_path=empty_dir,
        sds_path="/test/capture/empty",
        capture_type=CaptureType.DigitalRF,
        persist_state=test_state_persistence,
        verbose=False,
    )

    # ASSERT
    assert result is None


def test_upload_multichannel_drf_capture_dry_run(
    client: Client, tmp_path: Path, test_state_persistence: bool
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
        persist_state=test_state_persistence,
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
    client: Client,
    responses: responses.RequestsMock,
    tmp_path: Path,
    dry_run: bool,
    test_state_persistence: bool,
) -> None:
    """Test successful multi-channel DRF capture upload."""
    # ARRANGE
    client.dry_run = dry_run
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
            **_gateway_capture_sharing_fields(),
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
        persist_state=test_state_persistence,
    )

    # ASSERT
    assert captures is not None
    assert len(captures) == MULTICHANNEL_EXPECTED_COUNT
    for i, capture in enumerate(captures):
        assert capture.uuid == capture_uuids[i]
        assert capture.capture_type == CaptureType.DigitalRF
        assert capture.channel == channels[i]


def test_upload_multichannel_drf_capture_existing_capture(
    client: Client,
    responses: responses.RequestsMock,
    tmp_path: Path,
    dry_run: bool,
    test_state_persistence: bool,
) -> None:
    """Test multi-channel DRF capture when one capture already exists."""
    # ARRANGE
    client.dry_run = dry_run
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
            **_gateway_capture_sharing_fields(),
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
            **_gateway_capture_sharing_fields(),
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
        persist_state=test_state_persistence,
    )

    # ASSERT
    assert captures is not None
    assert len(captures) == MULTICHANNEL_EXPECTED_COUNT
    assert captures[0].uuid == existing_uuid
    assert captures[1].uuid == new_uuid


def test_upload_multichannel_drf_capture_creation_fails(
    client: Client,
    responses: responses.RequestsMock,
    tmp_path: Path,
    dry_run: bool,
    test_state_persistence: bool,
) -> None:
    """Test multi-channel DRF capture when capture creation fails for other reasons."""
    # ARRANGE
    client.dry_run = dry_run
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
            **_gateway_capture_sharing_fields(),
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
        persist_state=test_state_persistence,
        raise_on_error=False,
    )

    # ASSERT
    assert result == []


def test_capture_string_repr_nameless(sample_capture_data: dict[str, Any]) -> None:
    """Test the string representation of a capture."""
    # ARRANGE
    sample_capture_data.pop("name", None)  # ensure name is not set
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


def test_capture_string_repr_with_name(sample_capture_data: dict[str, Any]) -> None:
    """Test the string representation of a capture."""
    # ARRANGE
    sample_capture_data["name"] = "pytest-sample"
    capture: Capture = Capture.model_validate(sample_capture_data)

    # ACT
    capture_str = str(capture)
    capture_repr = repr(capture)

    # ASSERT
    log.info(capture_str)
    assert capture.name is not None, "Capture name should not be None for this test"
    assert capture.name in capture_str, (
        "Capture name should be in string representation"
    )
    assert f"type={capture.capture_type}" in capture_str
    assert f"files={len(capture.files)}" in capture_str
    assert capture.__class__.__name__ in capture_repr
    assert str(capture.uuid) in capture_repr


def test_delete_capture(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """Test deleting a capture."""
    # ARRANGE
    client.dry_run = dry_run
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


def test_delete_capture_raises_when_gateway_rejects_shared(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """DELETE fails with 400 when the capture is still shared (gateway message)."""
    client.dry_run = dry_run
    capture_uuid = uuidlib.uuid4()
    delete_url = get_captures_endpoint(client, capture_id=capture_uuid.hex)
    err_msg = "Cannot delete capture: revoke share permissions first."
    responses.add(
        method=responses.DELETE,
        url=delete_url,
        status=400,
        json={"detail": err_msg},
    )
    with pytest.raises(CaptureError) as exc_info:
        client.captures.delete(capture_uuid=capture_uuid)
    assert err_msg in str(exc_info.value)
    assert len(responses.calls) == 1


def test_delete_capture_raises_when_gateway_rejects_dataset_attachment(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """DELETE fails with 400 when the capture is still linked to datasets."""
    client.dry_run = dry_run
    capture_uuid = uuidlib.uuid4()
    delete_url = get_captures_endpoint(client, capture_id=capture_uuid.hex)
    err_msg = "Cannot delete capture: detach from datasets first."
    responses.add(
        method=responses.DELETE,
        url=delete_url,
        status=400,
        json={"detail": err_msg},
    )
    with pytest.raises(CaptureError) as exc_info:
        client.captures.delete(capture_uuid=capture_uuid)
    assert err_msg in str(exc_info.value)
    assert len(responses.calls) == 1


def test_delete_capture_dry_run(client: Client) -> None:
    """Test deleting a capture in dry run mode."""
    # ARRANGE
    client.dry_run = True
    capture_uuid = uuidlib.uuid4()

    # ACT
    result = client.captures.delete(capture_uuid=capture_uuid)

    # ASSERT
    assert result is True  # Dry run should simulate success


def test_revoke_capture_share_permissions(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """PUT revoke-share-permissions on a capture."""
    client.dry_run = dry_run
    capture_uuid = uuidlib.uuid4()
    revoke_url = get_capture_revoke_share_permissions_url(
        client, capture_id=capture_uuid.hex
    )
    responses.add(
        method=responses.PUT,
        url=revoke_url,
        status=200,
        json={"message": "Share permissions revoked successfully"},
    )

    assert client.captures.revoke_share_permissions(capture_uuid) is True
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "PUT"
    assert responses.calls[0].request.url == revoke_url


def test_detach_capture_from_datasets(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """PUT detach-from-datasets on a capture."""
    client.dry_run = dry_run
    capture_uuid = uuidlib.uuid4()
    detach_url = get_capture_detach_from_datasets_url(
        client, capture_id=capture_uuid.hex
    )
    responses.add(
        method=responses.PUT,
        url=detach_url,
        status=200,
        json={"message": "Capture detached from all connected datasets successfully"},
    )

    assert client.captures.detach_from_datasets(capture_uuid) is True
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "PUT"
    assert responses.calls[0].request.url == detach_url


def test_search_captures_freq_range(
    client: Client,
    responses: responses.RequestsMock,
    sample_capture_data: dict[str, Any],
    dry_run: bool,
) -> None:
    """Test searching captures with a frequency range query."""
    # ARRANGE
    client.dry_run = dry_run

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
    dry_run: bool,
) -> None:
    """Test searching captures with an exact match query."""
    # ARRANGE
    client.dry_run = dry_run

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


def test_upload_capture_with_name_dry_run(
    client: Client, tmp_path: Path, test_state_persistence: bool
) -> None:
    """Test upload_capture with name parameter in dry run mode."""
    # ARRANGE
    client.dry_run = True
    test_dir = tmp_path / "test_capture_with_name"
    test_dir.mkdir()
    (test_dir / "test_file.txt").write_text("test content")

    capture_name = "My Custom Capture Name"

    # ACT
    capture = client.upload_capture(
        capture_type=CaptureType.DigitalRF,
        channel="test_channel",
        local_path=test_dir,
        name=capture_name,
        persist_state=test_state_persistence,
        sds_path="/test/capture/with/name",
        verbose=False,
    )

    # ASSERT
    assert capture is not None
    assert capture.name == capture_name
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channel == "test_channel"


def test_upload_capture_without_name_dry_run(
    client: Client, tmp_path: Path, test_state_persistence: bool
) -> None:
    """Test upload_capture without name parameter in dry run mode."""
    # ARRANGE
    client.dry_run = True
    test_dir = tmp_path / "test_capture_no_name"
    test_dir.mkdir()
    (test_dir / "test_file.txt").write_text("test content")

    # ACT
    capture = client.upload_capture(
        capture_type=CaptureType.DigitalRF,
        channel="test_channel",
        local_path=test_dir,
        persist_state=test_state_persistence,
        sds_path="/test/capture/no/name",
        verbose=False,
    )

    # ASSERT
    assert capture is not None
    assert (
        capture.name == ""
    )  # Should be empty string in dry run mode when no name provided
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channel == "test_channel"


def test_create_capture_with_name(
    client: Client, responses: responses.RequestsMock, dry_run: bool
) -> None:
    """Test creating a capture with a custom name."""
    # ARRANGE
    client.dry_run = dry_run
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    channel = "channel1"
    capture_name = "Test Capture with Custom Name"
    capture_uuid = uuidlib.uuid4()

    # Mock response
    mocked_capture_response = {
        **_gateway_capture_sharing_fields(),
        "uuid": capture_uuid.hex,
        "capture_type": capture_type.value,
        "top_level_dir": str(top_level_dir),
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {},
        "channel": channel,
        "name": capture_name,
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
        name=capture_name,
    )

    # ASSERT
    assert capture.uuid == capture_uuid
    assert capture.capture_type == capture_type
    assert capture.top_level_dir == top_level_dir
    assert capture.channel == channel
    assert capture.name == capture_name
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "POST"
    assert responses.calls[0].request.url == get_captures_endpoint(client)

    # Verify that the name parameter was sent in the request
    if responses.calls[0].request.body:
        body = responses.calls[0].request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        assert isinstance(body, str)
        request_data = parse_qs(body)
        assert request_data["name"][0] == capture_name


def test_create_capture_with_name_dry_run(client: Client) -> None:
    """Test creating a capture with name in dry run mode."""
    # ARRANGE
    client.dry_run = True
    top_level_dir = PurePosixPath("/test/capture/directory")
    capture_type = CaptureType.DigitalRF
    capture_name = "Dry Run Test Capture"

    # ACT
    capture = client.captures.create(
        top_level_dir=top_level_dir,
        capture_type=capture_type,
        name=capture_name,
    )

    # ASSERT
    assert capture.uuid is not None
    assert capture.capture_type == capture_type
    assert capture.top_level_dir == top_level_dir
    assert capture.name == capture_name
    assert isinstance(capture.created_at, datetime), (
        "Expected created_at to be a datetime object"
    )
    assert len(capture.files) == 0


def test_create_capture_without_name_dry_run(client: Client) -> None:
    """Test creating a capture without name in dry run mode."""
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
    assert capture.name == ""  # Should be empty string when no name provided
    assert isinstance(capture.created_at, datetime), (
        "Expected created_at to be a datetime object"
    )
    assert len(capture.files) == 0


def test_upload_capture_with_name_success(
    client: Client,
    responses: responses.RequestsMock,
    tmp_path: Path,
    dry_run: bool,
    test_state_persistence: bool,
) -> None:
    """Test upload_capture with name parameter when upload succeeds."""
    # ARRANGE
    client.dry_run = dry_run
    test_dir = tmp_path / "test_capture_success"
    test_dir.mkdir()
    (test_dir / "test_file.txt").write_text("test content")

    capture_name = "Successful Upload Capture"
    capture_uuid = uuidlib.uuid4()

    # Mock content check endpoint
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

    # Mock file upload
    add_file_upload_mock(client, responses, directory="/test/upload/success")

    # Mock capture creation
    mocked_capture_response = {
        **_gateway_capture_sharing_fields(),
        "uuid": capture_uuid.hex,
        "capture_type": CaptureType.DigitalRF.value,
        "top_level_dir": "/test/upload/success",
        "index_name": "captures-drf",
        "origin": CaptureOrigin.User.value,
        "capture_props": {},
        "channel": "test_channel",
        "name": capture_name,
        "files": [],
    }

    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=201,
        json=mocked_capture_response,
    )

    # ACT
    capture = client.upload_capture(
        capture_type=CaptureType.DigitalRF,
        channel="test_channel",
        local_path=test_dir,
        name=capture_name,
        persist_state=test_state_persistence,
        sds_path="/test/upload/success",
        verbose=False,
    )

    # ASSERT
    assert capture is not None
    assert capture.uuid == capture_uuid
    assert capture.name == capture_name
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channel == "test_channel"

    # Verify that the name parameter was sent in the capture creation request
    capture_requests = [
        call
        for call in responses.calls
        if call.request.url
        and "/captures" in call.request.url
        and call.request.method == "POST"
    ]
    assert len(capture_requests) == 1
    if capture_requests[0].request.body:
        body = capture_requests[0].request.body
        if isinstance(body, bytes):
            body = body.decode("utf-8")
        assert isinstance(body, str)
        request_data = parse_qs(body)
        assert request_data["name"][0] == capture_name


# ── Create method edge cases ────────────────────────────────────────────────


def test_create_capture_deprecation_warning(
    loguru_caplog: io.StringIO,
) -> None:
    """Deprecation warning is logged when index_name is provided to create()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    api.create(
        top_level_dir=PurePosixPath("/test"),
        capture_type=CaptureType.DigitalRF,
        index_name="custom-index",
    )

    output = loguru_caplog.getvalue()
    assert "The 'index_name' parameter is deprecated" in output


def test_create_capture_unknown_capture_type_warning(
    loguru_caplog: io.StringIO,
) -> None:
    """Warning when capture_type is not in index_mapping and index_name is empty."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    api.create(
        top_level_dir=PurePosixPath("/test"),
        capture_type=CaptureType.SigMF,
    )

    output = loguru_caplog.getvalue()
    assert "Could not find an index for capture_type" in output


def test_create_capture_verbose_logging(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging in create() before and after gateway call."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    capture = api.create(
        top_level_dir=PurePosixPath("/test"),
        capture_type=CaptureType.DigitalRF,
    )

    assert capture is not None
    # verbose branch executed: records were emitted (count, not exact-text coupling)
    assert loguru_caplog.getvalue()


# ── Listing method edge cases ───────────────────────────────────────────────


def test_listing_captures_has_more_warning(
    loguru_caplog: io.StringIO,
) -> None:
    """Warning logged when 'next' has a non-empty URL (has_more=True)."""
    payload = _build_drf_capture_payload()
    payload["next"] = "http://example.com/next"
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = api.listing()

    assert len(captures) == 1
    output = loguru_caplog.getvalue()
    assert "Not all capture results may be listed" in output


def test_listing_captures_verbose_logging(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging in listing()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload={"results": [payload], "next": None})
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    captures = api.listing()

    assert len(captures) == 1
    assert loguru_caplog.getvalue()


# ── Update method edge cases ────────────────────────────────────────────────


def test_update_capture_verbose_logging(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging emits records during update() (count, not exact text)."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    api.update(capture_uuid=uuid4())

    assert loguru_caplog.getvalue() != ""


# ── Read method edge cases ──────────────────────────────────────────────────


def test_read_capture_verbose_logging(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging emits records during read() (count, not exact text)."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    capture = api.read(capture_uuid=uuid4())

    assert capture is not None
    assert loguru_caplog.getvalue() != ""


# ── Delete method edge cases ────────────────────────────────────────────────


def test_delete_capture_verbose_logging(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging emits records during delete() (count, not exact text)."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    result = api.delete(capture_uuid=uuid4())

    assert result is True
    assert loguru_caplog.getvalue() != ""


# ── revoke_share_permissions edge cases ─────────────────────────────────────


def test_revoke_share_permissions_verbose(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging emits records in revoke_share_permissions()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    result = api.revoke_share_permissions(capture_uuid=uuid4())

    assert result is True
    assert loguru_caplog.getvalue() != ""


def test_revoke_share_permissions_dry_run_verbose(
    loguru_caplog: io.StringIO,
) -> None:
    """Dry-run + verbose path emits records in revoke_share_permissions()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=True,
        verbose=True,
    )

    result = api.revoke_share_permissions(capture_uuid=uuid4())

    assert result is True
    assert loguru_caplog.getvalue() != ""


# ── detach_from_datasets edge cases ─────────────────────────────────────────


def test_detach_from_datasets_verbose(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging emits records in detach_from_datasets()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    result = api.detach_from_datasets(capture_uuid=uuid4())

    assert result is True
    assert loguru_caplog.getvalue() != ""


def test_detach_from_datasets_dry_run_verbose(
    loguru_caplog: io.StringIO,
) -> None:
    """Dry-run + verbose path emits records in detach_from_datasets()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=True,
        verbose=True,
    )

    result = api.detach_from_datasets(capture_uuid=uuid4())

    assert result is True
    assert loguru_caplog.getvalue() != ""


# ── advanced_search edge cases ──────────────────────────────────────────────


def test_advanced_search_no_results_key() -> None:
    """advanced_search raises CaptureError when 'results' is missing."""
    payload = {"not_results": "something else"}
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    with pytest.raises(CaptureError, match="Unexpected search result format"):
        api.advanced_search(
            field_path="capture_props.center_freq",
            query_type="range",
            filter_value={"gte": 1, "lte": 2},
        )


def test_advanced_search_validation_error(
    loguru_caplog: io.StringIO,
) -> None:
    """Validation errors during advanced_search are logged and skipped."""
    valid = _build_drf_capture_payload(name="valid_payload")
    invalid = _build_drf_capture_payload(name="invalid_payload")
    invalid.pop("capture_type")  # Make it fail validation

    payload = {"results": [valid, invalid]}
    gateway = _GatewayStub(payload=payload)
    api = CaptureAPI(gateway=cast("GatewayClient", gateway), dry_run=False)

    captures = api.advanced_search(
        field_path="capture_props.center_freq",
        query_type="range",
        filter_value={"gte": 1, "lte": 2},
    )

    assert len(captures) == 1
    assert captures[0].name == "valid_payload"
    # State proves the invalid payload was skipped; the skip-warning path is exercised
    # (loguru, via log_user_warning). Pin that a record was emitted, not its exact text.
    assert loguru_caplog.getvalue(), "expected a validation-skip warning record"


def test_advanced_search_verbose_logging(
    loguru_caplog: io.StringIO,
) -> None:
    """Verbose logging in advanced_search()."""
    payload = _build_drf_capture_payload()
    gateway = _GatewayStub(payload={"results": [payload]})
    api = CaptureAPI(
        gateway=cast("GatewayClient", gateway),
        dry_run=False,
        verbose=True,
    )

    captures = api.advanced_search(
        field_path="capture_props.center_freq",
        query_type="range",
        filter_value={"gte": 1, "lte": 2},
    )

    assert len(captures) == 1
    assert loguru_caplog.getvalue() != ""


# ── _extract_page_from_payload helper ───────────────────────────────────────


def test_extract_page_from_payload_dict_with_next() -> None:
    """Dict result (no 'results' key) with non-empty 'next' URL."""
    payload = _build_drf_capture_payload()
    payload["next"] = "http://example.com/next"

    result, has_more = extract(json.dumps(payload).encode("utf-8"))

    assert has_more is True  # line 423
    assert isinstance(result, list)
    assert len(result) == 1  # line 427
    assert result[0]["uuid"] == payload["uuid"]


def test_extract_page_from_payload_dict_with_empty_next() -> None:
    """Dict result (no 'results' key) with empty 'next' URL."""
    payload = _build_drf_capture_payload()
    payload["next"] = ""

    result, has_more = extract(json.dumps(payload).encode("utf-8"))

    assert has_more is False
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["uuid"] == payload["uuid"]


class _GatewayStub:
    """Minimal stub that emulates the gateway list endpoint."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.calls = 0

    def list_captures(self, capture_type: CaptureType | None = None) -> bytes:
        del capture_type  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")

    def create_capture(self, **kwargs: object) -> bytes:
        del kwargs  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")

    def read_capture(self, **kwargs: object) -> bytes:
        del kwargs  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")

    def update_capture(self, **kwargs: object) -> bytes:
        del kwargs  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")

    def delete_capture(self, **kwargs: object) -> None:
        del kwargs  # unused in tests
        self.calls += 1

    def revoke_capture_share_permissions(self, **kwargs: object) -> bytes:
        del kwargs  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")

    def detach_capture_from_datasets(self, **kwargs: object) -> bytes:
        del kwargs  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")

    def captures_advanced_search(self, **kwargs: object) -> bytes:
        del kwargs  # unused in tests
        self.calls += 1
        return json.dumps(self._payload).encode("utf-8")
