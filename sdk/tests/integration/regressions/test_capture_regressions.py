"""Regression tests for capture functionality."""

from pathlib import Path

import pytest
from spectrumx.client import Client
from spectrumx.errors import CaptureError
from spectrumx.models.captures import CaptureType
from spectrumx.utils import get_random_line

from tests.integration.conftest import PassthruEndpoints
from tests.integration.test_captures import drf_channel


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
        ]
    ],
    indirect=True,
)
def test_capture_backward_compatibility_channel_parameter(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Test that the SDK still accepts the legacy 'channel' parameter for
    backward compatibility.
    """

    # ARRANGE
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = f"/test-backward-compat-{random_suffix}"

    # ACT - Try to create capture with legacy 'channel' parameter
    # This should work because the SDK converts single channel to channels list
    capture = integration_client.upload_capture(
        local_path=drf_sample_top_level_dir,
        sds_path=sds_path,
        capture_type=CaptureType.DigitalRF,
        channel=drf_channel,  # Legacy parameter
    )

    # ASSERT
    assert capture is not None
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channels == [drf_channel], (
        "Channels should be converted from single channel"
    )
    assert capture.channel == drf_channel, (
        "Primary channel should be the provided channel"
    )

    # Clean up
    integration_client.captures.delete(capture_uuid=capture.uuid)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
        ]
    ],
    indirect=True,
)
def test_capture_multi_channel_validation(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Test that multi-channel captures are properly validated and stored."""

    # ARRANGE
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = f"/test-multi-channel-{random_suffix}"
    multi_channels = ["channel-1", "channel-2", "channel-3"]

    # ACT
    capture = integration_client.upload_capture(
        local_path=drf_sample_top_level_dir,
        sds_path=sds_path,
        capture_type=CaptureType.DigitalRF,
        channels=multi_channels,
    )

    # Constants
    expected_channel_count = 3

    # ASSERT
    assert capture is not None
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channels == multi_channels, "Channels should match the provided list"
    assert capture.channel == multi_channels[0], (
        "Primary channel should be the first channel"
    )
    assert len(capture.channels) == expected_channel_count, (
        "Should have exactly 3 channels"
    )

    # Test that all channels are accessible
    for _, channel in enumerate(multi_channels):
        assert channel in capture.channels, (
            f"Channel {channel} should be in channels list"
        )

    # Clean up
    integration_client.captures.delete(capture_uuid=capture.uuid)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
        ]
    ],
    indirect=True,
)
def test_capture_empty_channels_validation(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Test that empty channels list is properly rejected."""

    # ARRANGE
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = f"/test-empty-channels-{random_suffix}"

    # ACT & ASSERT - Empty channels list should be rejected
    with pytest.raises(CaptureError):
        integration_client.upload_capture(
            local_path=drf_sample_top_level_dir,
            sds_path=sds_path,
            capture_type=CaptureType.DigitalRF,
            channels=[],  # Empty channels list
        )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
        ]
    ],
    indirect=True,
)
def test_capture_legacy_data_compatibility(
    integration_client: Client,
) -> None:
    """Test that existing captures with legacy channel format are still readable."""

    # ARRANGE - Get existing captures
    captures = integration_client.captures.listing(
        capture_type=CaptureType.DigitalRF,
    )

    if not captures:
        pytest.skip(
            "No existing DigitalRF captures found for legacy compatibility test"
        )

    # ACT & ASSERT - Check that existing captures are still readable
    for capture in captures:
        assert capture.uuid is not None, "Capture UUID should not be None"
        assert capture.capture_type == CaptureType.DigitalRF

        # Legacy captures should still have channel field populated
        assert capture.channel is not None, "Legacy capture should have channel field"

        # Channels field should be populated (either from legacy data or computed)
        assert capture.channels is not None, "Channels field should be populated"
        assert isinstance(capture.channels, list), "Channels should be a list"
        assert len(capture.channels) > 0, "Channels list should not be empty"

        # Primary channel should be in channels list
        assert capture.channel in capture.channels, (
            "Primary channel should be in channels list"
        )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
        ]
    ],
    indirect=True,
)
def test_capture_channel_consistency(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Test that channel and channels fields are consistent across operations."""

    # ARRANGE
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = f"/test-channel-consistency-{random_suffix}"
    test_channels = ["primary-channel", "secondary-channel"]

    # ACT - Create capture
    capture = integration_client.upload_capture(
        local_path=drf_sample_top_level_dir,
        sds_path=sds_path,
        capture_type=CaptureType.DigitalRF,
        channels=test_channels,
    )

    # ASSERT - Check consistency after creation
    assert capture.channels == test_channels, "Channels should match input"
    assert capture.channel == test_channels[0], "Primary channel should be first"

    # ACT - Read the capture back
    read_capture = integration_client.captures.read(
        capture_uuid=capture.uuid,
    )

    # ASSERT - Check consistency after reading
    assert read_capture.channels == test_channels, (
        "Channels should be consistent after read"
    )
    assert read_capture.channel == test_channels[0], (
        "Primary channel should be consistent after read"
    )
    assert read_capture.channels == capture.channels, (
        "Channels should match between create and read"
    )
    assert read_capture.channel == capture.channel, (
        "Primary channel should match between create and read"
    )

    # Clean up
    integration_client.captures.delete(capture_uuid=capture.uuid)
