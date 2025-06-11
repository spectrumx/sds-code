"""Tests for SDS Captures."""

import json
from collections.abc import Generator
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any

import pytest
from loguru import logger as log
from pydantic import BaseModel
from spectrumx.client import Client
from spectrumx.errors import CaptureError
from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureType
from spectrumx.utils import get_random_line

from tests.integration.conftest import PassthruEndpoints
from tests.integration.conftest import dir_integration_data

log.trace("Placeholder log avoid reimporting or resolving unused import warnings.")

# paths with test data
drf_channel = "cap-2024-06-27T14-00-00"


@pytest.fixture
def _capture_test(drf_sample_top_level_dir: Path) -> Generator[None]:
    """Choose to run capture test or not, based on existing data."""
    if not drf_sample_top_level_dir.exists():
        pytest.skip(
            "Capture test SKIPPED. Test data does not "
            f"exist at: '{drf_sample_top_level_dir}'"
        )

    # yield control to the test
    yield

    # teardown code for integration tests

    return


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
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
def test_capture_creation_drf(
    integration_client: Client, drf_sample_top_level_dir: Path
) -> None:
    """Tests creating a Digital-RF capture."""

    # ARRANGE
    cap_data = _upload_drf_capture_test_assets(
        integration_client=integration_client,
        drf_sample_top_level_dir=drf_sample_top_level_dir,
    )

    # ACT

    # create a capture
    capture = integration_client.captures.create(
        top_level_dir=cap_data.capture_top_level,
        channel=cap_data.drf_channel,
        capture_type=CaptureType.DigitalRF,
    )

    # ASSERT

    # basic capture information
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channel == drf_channel
    assert capture.top_level_dir == cap_data.capture_top_level

    # test capture properties
    assert capture.capture_props["start_bound"] == cap_data.cap_start_bound
    assert capture.capture_props["is_continuous"] == cap_data.cap_is_continuous
    assert (
        capture.capture_props["custom_attrs"]["receiver/info/mboard_serial"]
        == cap_data.cap_serial
    )


class DRFCaptureAssets(BaseModel):
    """Holds Digital-RF capture assets to ease uploads and capture creations."""

    cap_is_continuous: bool
    cap_serial: str
    cap_start_bound: int
    drf_channel: str
    path_after_capture_data: PurePosixPath

    @property
    def capture_top_level(self) -> PurePosixPath:
        """Constructs the full path for the capture on the SDS."""
        return PurePosixPath("/") / self.path_after_capture_data


def _upload_drf_capture_test_assets(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> DRFCaptureAssets:
    """Helper to package and upload Digital-RF capture assets to SDS."""
    cap_start_bound: int = 1_719_499_740
    cap_is_continuous: bool = True
    cap_serial: str = "31649FE"

    # define paths in the context of a capture
    dir_top_level = drf_sample_top_level_dir
    dir_channel = drf_sample_top_level_dir / drf_channel
    dir_metadata = dir_channel / "metadata"
    assert dir_metadata.is_dir(), (
        "Metadata directory should exist; check that "
        f"you have the right paths set: '{dir_metadata}'"
    )

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    path_after_capture_data = dir_top_level.relative_to(dir_integration_data)
    random_suffix = get_random_line(10, include_punctuation=False)
    path_after_capture_data = (
        PurePosixPath(path_after_capture_data) / f"test-{random_suffix}"
    )

    _upload_assets(
        integration_client=integration_client,
        sds_path=path_after_capture_data,
        local_path=dir_top_level,
    )

    return DRFCaptureAssets(
        cap_is_continuous=cap_is_continuous,
        cap_serial=cap_serial,
        cap_start_bound=cap_start_bound,
        drf_channel=drf_channel,
        path_after_capture_data=path_after_capture_data,
    )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
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
def test_capture_creation_rh(
    integration_client: Client,
    rh_sample_top_level_dir: Path,
) -> None:
    """Tests creating a RadioHound capture."""

    # ARRANGE
    radiohound_data = load_rh_data(rh_sample_top_level_dir)
    scan_group = radiohound_data["scan_group"]

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    rel_path_capture = rh_sample_top_level_dir.relative_to(dir_integration_data)
    random_suffix = get_random_line(10, include_punctuation=False)
    rel_path_capture = PurePosixPath(rel_path_capture) / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=rel_path_capture,
        local_path=rh_sample_top_level_dir,
    )

    # ACT

    # delete all captures with that scan group to avoid conflicts
    _delete_rh_captures_by_scan_group(
        integration_client=integration_client,
        scan_group=scan_group,
    )

    capture_top_level = PurePosixPath("/") / rel_path_capture
    capture = integration_client.captures.create(
        top_level_dir=capture_top_level,
        scan_group=scan_group,
        capture_type=CaptureType.RadioHound,
    )

    # ASSERT

    # basic capture information
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.RadioHound
    assert capture.top_level_dir == capture_top_level

    # test capture metadata
    assert capture.scan_group is not None, "Scan group should not be None"
    assert str(capture.scan_group) == radiohound_data["scan_group"], (
        "Scan group was not set correctly for RadioHound capture"
    )
    assert capture.capture_props, "Capture properties should not be empty"
    assert capture.capture_props == radiohound_data, (
        "Capture props doesn't match the reference data: \n"
        f"'{capture.capture_props}'\n!=\n'{radiohound_data}'"
    )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.capture_listing(),
        ]
    ],
    indirect=True,
)
def test_capture_listing_drf(integration_client: Client) -> None:
    """Tests reading and listing Digital-RF captures."""
    captures = integration_client.captures.listing(
        capture_type=CaptureType.DigitalRF,
    )
    assert len(captures) > 0, "At least one capture should be present"
    for capture in captures:
        assert capture.uuid is not None, "Capture UUID should not be None"
        assert capture.capture_type == CaptureType.DigitalRF
        assert capture.channel is not None, "DigitalRF capture should have a channel"
        assert capture.top_level_dir is not None, "Top level dir should not be None"


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.capture_listing(),
        ]
    ],
    indirect=True,
)
def test_capture_listing_rh(integration_client: Client) -> None:
    """Tests reading and listing RadioHound captures."""
    captures = integration_client.captures.listing(
        capture_type=CaptureType.RadioHound,
    )
    assert len(captures) > 0, "At least one capture should be present"
    for capture in captures:
        assert capture.uuid is not None, "Capture UUID should not be None"
        assert capture.capture_type == CaptureType.RadioHound
        assert not capture.channel, "RadioHound capture should not have a channel"
        assert capture.top_level_dir is not None, "Top level dir should not be None"


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.capture_listing(),
            *PassthruEndpoints.capture_creation(),
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
        ]
    ],
    indirect=True,
)
def test_capture_listing_all(integration_client: Client) -> None:
    """Tests reading and listing all types of captures."""
    # create a capture if none are present
    captures = integration_client.captures.listing()
    if not captures:
        _create_rh_capture(
            rh_sample_top_level_dir=dir_integration_data / "captures" / "radiohound",
            integration_client=integration_client,
        )
        captures = integration_client.captures.listing()
    assert len(captures) > 0, "At least one capture should be present"
    for capture in captures:
        assert capture.uuid is not None, "Capture UUID should not be None"
        assert capture.capture_type in CaptureType.__members__.values(), (
            "Capture type should be one of the known types: "
            f"{CaptureType.__members__.values()}"
        )
        assert capture.top_level_dir is not None, "Top level dir should not be None"
        assert capture.created_at is not None, (
            "Capture created_at timestamp should not be None"
        )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
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
def test_capture_update_rh(
    integration_client: Client,
    rh_sample_top_level_dir: Path,
) -> None:
    """Tests updating a RadioHound capture."""

    # ARRANGE by uploading capture data and creating one
    radiohound_data = load_rh_data(rh_sample_top_level_dir)

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    rh_capture_update_sds_path = rh_sample_top_level_dir.relative_to(
        dir_integration_data
    )
    random_suffix = get_random_line(10, include_punctuation=False)
    rh_capture_update_sds_path = (
        PurePosixPath(rh_capture_update_sds_path) / f"test-{random_suffix}"
    )

    _upload_assets(
        integration_client=integration_client,
        sds_path=rh_capture_update_sds_path,
        local_path=rh_sample_top_level_dir,
    )

    # delete all captures with that scan group to avoid conflicts
    assert "scan_group" in radiohound_data, (
        "Expected 'scan_group' in the RadioHound data"
    )
    scan_group = radiohound_data["scan_group"]
    _delete_rh_captures_by_scan_group(
        integration_client=integration_client,
        scan_group=scan_group,
    )

    capture_top_level = PurePosixPath("/") / rh_capture_update_sds_path
    capture = integration_client.captures.create(
        top_level_dir=capture_top_level,
        scan_group=scan_group,
        capture_type=CaptureType.RadioHound,
    )

    # certify the capture was created
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.RadioHound
    assert capture.top_level_dir == capture_top_level
    assert capture.capture_props, "Capture properties should not be empty"
    assert capture.capture_props == radiohound_data, (
        "Capture props doesn't match the reference data: \n"
        f"'{capture.capture_props}'\n!=\n'{radiohound_data}'"
    )

    # upload a new radiohound file
    new_dir_top_level = dir_integration_data / "captures" / "radiohound-update"
    new_radiohound_file = new_dir_top_level / "reference-v0-addendum.rh.json"
    assert new_radiohound_file.is_file(), (
        "New reference file should exist; check that "
        f"you have the right paths set: '{new_radiohound_file}'"
    )

    _upload_assets(
        integration_client=integration_client,
        sds_path=rh_capture_update_sds_path,
        local_path=new_dir_top_level,
    )

    # ACT by updating the capture

    # update the capture
    integration_client.captures.update(
        capture_uuid=capture.uuid,
    )

    # ASSERT capture was updated

    # reading the capture should now return 2 files
    read_capture = integration_client.captures.read(
        capture_uuid=capture.uuid,
    )
    assert read_capture.files, "Expected a list of files associated to this capture"
    num_files = 2  # the original file + the new one
    assert len(read_capture.files) == num_files, (
        "Expected 2 files associated to this capture after update"
    )


def load_rh_data(rh_top_level_dir: Path) -> dict[str, Any]:
    """Helper to load RadioHound data from a top-level directory."""
    radiohound_file = rh_top_level_dir / "reference-v0.rh.json"
    assert radiohound_file.is_file(), (
        "Reference file should exist; check that "
        f"you have the right paths set: '{radiohound_file}'"
    )
    with radiohound_file.open("r") as fp_json:
        return json.load(fp_json)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
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
def test_capture_upload_drf(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Tests uploading and creating a Digital-RF capture in one operation."""
    # ARRANGE a new directory to upload as capture
    test_dir = drf_sample_top_level_dir
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = f"/test-upload-capture-{random_suffix}"
    capture_type = CaptureType.DigitalRF

    # ACT by uploading the capture
    capture = integration_client.upload_capture(
        local_path=test_dir,
        sds_path=sds_path,
        capture_type=capture_type,
        channel=drf_channel,
    )

    # ASSERT capture was correctly created
    assert capture is not None
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == capture_type
    assert capture.channel == drf_channel
    assert str(capture.top_level_dir) == sds_path
    assert capture.capture_props["is_continuous"] is True
    assert "start_bound" in capture.capture_props
    assert "custom_attrs" in capture.capture_props

    # Clean up
    integration_client.captures.delete(capture_uuid=capture.uuid)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
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
def test_capture_upload_rh(integration_client: Client) -> None:
    """Tests uploading and creating a RadioHound capture in one operation."""
    # ARRANGE
    dir_top_level = dir_integration_data / "captures" / "radiohound"
    radiohound_file = dir_top_level / "reference-v0.rh.json"
    assert radiohound_file.is_file(), (
        f"Reference file should exist at '{radiohound_file}'"
    )

    with radiohound_file.open("r") as fp_json:
        radiohound_data = json.load(fp_json)

    scan_group = radiohound_data["scan_group"]
    _delete_rh_captures_by_scan_group(
        integration_client=integration_client,
        scan_group=scan_group,
    )
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = f"/test-upload-rh-{random_suffix}"

    # ACT
    capture = integration_client.upload_capture(
        local_path=dir_top_level,
        sds_path=sds_path,
        capture_type=CaptureType.RadioHound,
        scan_group=scan_group,
    )

    # ASSERT
    assert capture is not None
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.RadioHound
    assert str(capture.top_level_dir) == sds_path
    assert str(capture.scan_group) == scan_group

    # Test capture props match the reference data
    assert capture.capture_props == radiohound_data, (
        "Capture props doesn't match the reference data"
    )

    # Clean up
    integration_client.captures.delete(capture_uuid=capture.uuid)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
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
def test_capture_upload_missing_required_fields_drf(
    integration_client: Client, drf_sample_top_level_dir: Path
) -> None:
    """When lacking required fields, a DRF capture creation will fail.

    Note the file uploads are still expected to succeed.
    """
    # ARRANGE to upload assets for a Digital-RF capture
    test_dir = drf_sample_top_level_dir
    random_suffix = get_random_line(10, include_punctuation=False)
    sds_path = PurePosixPath(f"/test-upload-capture-{random_suffix}")
    capture_type = CaptureType.DigitalRF
    _upload_assets(
        integration_client=integration_client,
        sds_path=sds_path,
        local_path=test_dir,
    )

    # ACT & ASSERT - Missing channel for DigitalRF
    with pytest.raises(CaptureError):
        integration_client.upload_capture(
            local_path=test_dir,
            sds_path=sds_path,
            capture_type=capture_type,
            # Missing required channel parameter
        )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
            *PassthruEndpoints.capture_reading(),
        ]
    ],
    indirect=True,
)
def test_capture_reading_drf(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Tests reading a specific Digital-RF capture."""

    # ARRANGE

    # define paths in the context of a capture
    dir_top_level = drf_sample_top_level_dir
    dir_channel = dir_top_level / drf_channel
    dir_metadata = dir_channel / "metadata"
    assert dir_metadata.is_dir(), (
        "Metadata directory should exist; check that "
        f"you have the right paths set: '{dir_metadata}'"
    )

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    path_after_capture_data = dir_top_level.relative_to(dir_integration_data)
    random_suffix = get_random_line(10, include_punctuation=False)
    path_after_capture_data = path_after_capture_data / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=path_after_capture_data,
        local_path=dir_top_level,
    )
    capture = integration_client.captures.create(
        top_level_dir=Path(f"/{path_after_capture_data}"),
        channel=drf_channel,
        capture_type=CaptureType.DigitalRF,
    )
    assert capture.uuid is not None, "UUID of new capture should not be None"

    # ACT
    read_capture = integration_client.captures.read(
        capture_uuid=capture.uuid,
    )

    # ASSERT

    # basic capture information
    assert read_capture.files, "Expected a list of files associated to this capture"
    assert read_capture.uuid == capture.uuid, "Capture UUID should match"
    assert read_capture.capture_type == CaptureType.DigitalRF
    assert read_capture.channel == drf_channel
    assert read_capture.top_level_dir == Path(f"/{path_after_capture_data}")

    # test capture properties
    assert read_capture.capture_props == capture.capture_props, (
        "Capture properties should match the created capture"
    )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
            *PassthruEndpoints.capture_deletion(),
        ]
    ],
    indirect=True,
)
def test_capture_deletion(
    integration_client: Client, drf_sample_top_level_dir: Path
) -> None:
    """Tests deleting a capture."""

    # ARRANGE
    cap_data = _upload_drf_capture_test_assets(
        integration_client=integration_client,
        drf_sample_top_level_dir=drf_sample_top_level_dir,
    )
    capture = integration_client.captures.create(
        top_level_dir=cap_data.capture_top_level,
        capture_type=CaptureType.DigitalRF,
        channel=cap_data.drf_channel,
    )

    # ACT
    assert capture.uuid is not None, "UUID of new capture should not be None"
    result = integration_client.captures.delete(capture_uuid=capture.uuid)

    # ASSERT
    assert result is True, "Capture deletion should return True"
    with pytest.raises(CaptureError):
        integration_client.captures.read(
            capture_uuid=capture.uuid,
        )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
            *PassthruEndpoints.capture_search(),
        ]
    ],
    indirect=True,
)
def test_capture_advanced_search_frequency_range(
    integration_client: Client,
    drf_sample_top_level_dir: Path,
) -> None:
    """Tests searching captures with a frequency range query."""
    # ARRANGE to create a capture
    cap_data = _upload_drf_capture_test_assets(
        integration_client=integration_client,
        drf_sample_top_level_dir=drf_sample_top_level_dir,
    )
    capture = integration_client.captures.create(
        top_level_dir=cap_data.capture_top_level,
        channel=cap_data.drf_channel,
        capture_type=CaptureType.DigitalRF,
    )
    center_freq = capture.capture_props.get("center_frequencies")
    assert center_freq is not None, (
        "Expected 'center_frequencies' in capture properties"
    )
    assert isinstance(center_freq, list), "Expected 'center_frequencies' to be a list"
    assert len(center_freq) > 0, (
        "Expected 'center_frequencies' to have at least one value"
    )
    center_freq = center_freq[0]  # take the first frequency for testing
    test_freq_lower = center_freq - 1_234_567
    test_freq_upper = center_freq + 1_000_000

    # ACT by searching the new capture
    field_path = "capture_props.center_frequencies"
    query_type = "range"
    filter_value = {"gte": test_freq_lower, "lte": test_freq_upper}

    matched_caps = integration_client.captures.advanced_search(
        field_path=field_path,
        query_type=query_type,
        filter_value=filter_value,
    )
    is_capture_found = any(match.uuid == capture.uuid for match in matched_caps)

    # ASSERT the capture was found
    assert capture.uuid is not None, "UUID of new capture should not be None"
    assert len(matched_caps) > 0, (
        "Should find at least one capture in the frequency range"
    )
    assert is_capture_found, (
        f"Should find our test capture (UUID: {capture.uuid}) in search results"
    )

    integration_client.captures.delete(capture_uuid=capture.uuid)


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_capture_test")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_uploads(),
            *PassthruEndpoints.capture_creation(),
            *PassthruEndpoints.capture_search(),
        ]
    ],
    indirect=True,
)
def test_capture_advanced_search_full_text_search(
    integration_client: Client, drf_sample_top_level_dir: Path
) -> None:
    """Tests searching captures with a full-text search query.

    Digital-RF capture props example for reference:

    ```
    'capture_props': {
        'samples_per_second': 2500000,
        'start_bound': 1719499740,
        'end_bound': 1719499741,
        'is_complex': True,
        'is_continuous': True,
        'center_freq': 1024000000,
        'bandwidth': 100000000,
        'custom_attrs': {
            'num_subchannels': 1,
            'index': 4298748970000000,
            'processing/channelizer_filter_taps': [],
            'processing/decimation': 1,
            'processing/interpolation': 1,
            'processing/resampling_filter_taps': [],
            'processing/scaling': 1.0,
            'receiver/center_freq': 1024000000.4842604,
            'receiver/clock_rate': 125000000.0,
            'receiver/clock_source': 'external',
            'receiver/dc_offset': False,
            'receiver/description': 'UHD USRP source using GNU Radio',
            'receiver/id': '172.16.20.43',
            'receiver/info/mboard_id': 'n310',
            'receiver/info/mboard_name': 'n/a',
            'receiver/info/mboard_serial': '31649FE',
            'receiver/info/rx_antenna': 'RX2',
            'receiver/info/rx_id': '336',
            'receiver/info/rx_serial': '3162222',
            'receiver/info/rx_subdev_name': 'Magnesium',
            'receiver/info/rx_subdev_spec': 'A:0 A:1',
            'receiver/iq_balance': '',
            'receiver/lo_export': '',
            'receiver/lo_offset': 624999.4039535522,
            'receiver/lo_source': '',
            'receiver/otw_format': 'sc16',
            'receiver/samp_rate': 2500000.0,
            'receiver/stream_args': '',
            'receiver/subdev': 'A:0',
            'receiver/time_source': 'external',
        },
    },
    ```

    """
    # ARRANGE
    cap_data = _upload_drf_capture_test_assets(
        integration_client=integration_client,
        drf_sample_top_level_dir=drf_sample_top_level_dir,
    )
    capture = integration_client.captures.create(
        top_level_dir=cap_data.capture_top_level,
        channel=cap_data.drf_channel,
        capture_type=CaptureType.DigitalRF,
    )

    # ACT
    field_path = "capture_props.custom_attrs.receiver/description"
    query_type = "match"  # 'match' for full-text search
    filter_value = "UHD USRP"

    matched_caps = integration_client.captures.advanced_search(
        field_path=field_path,
        query_type=query_type,
        filter_value=filter_value,
    )
    is_capture_found = any(match.uuid == capture.uuid for match in matched_caps)

    # ASSERT
    assert len(matched_caps) > 0, "Should find at least one capture with the tag"
    assert is_capture_found, (
        f"Could not find our test capture '{capture.uuid}' in search results"
    )

    if capture.uuid:
        integration_client.captures.delete(capture_uuid=capture.uuid)


def _upload_assets(
    integration_client: Client,
    sds_path: Path | PurePosixPath,
    local_path: Path,
) -> None:
    """Helper to upload a local directory to SDS and assert success."""
    log.debug(f"Uploading assets as '/{sds_path}'")
    upload_results = integration_client.upload(
        local_path=local_path,
        sds_path=sds_path,
        verbose=False,
    )
    success_results = [success for success in upload_results if success]
    failed_results = [success for success in upload_results if not success]
    assert len(failed_results) == 0, (
        f"No failed uploads should be present: {failed_results}"
    )
    log.debug(f"Uploaded {len(success_results)} assets.")


def _create_rh_capture(
    rh_sample_top_level_dir: Path,
    integration_client: Client,
) -> Capture:
    """Helper to create a RadioHound capture.

    Note this deletes all existing RH captures under this user with the same scan group.
    """
    # ARRANGE
    radiohound_data = load_rh_data(rh_sample_top_level_dir)
    scan_group = radiohound_data["scan_group"]

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    rel_path_capture = rh_sample_top_level_dir.relative_to(dir_integration_data)
    random_suffix = get_random_line(10, include_punctuation=False)
    rel_path_capture = PurePosixPath(rel_path_capture) / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=rel_path_capture,
        local_path=rh_sample_top_level_dir,
    )

    # delete all captures with that scan group to avoid conflicts
    _delete_rh_captures_by_scan_group(
        integration_client=integration_client,
        scan_group=scan_group,
    )

    capture_top_level = PurePosixPath("/") / rel_path_capture
    return integration_client.captures.create(
        top_level_dir=capture_top_level,
        scan_group=scan_group,
        capture_type=CaptureType.RadioHound,
    )


def _delete_rh_captures_by_scan_group(
    integration_client: Client, scan_group: str
) -> None:
    """Helper to delete all RadioHound captures with a specific scan group."""
    captures = integration_client.captures.listing(
        capture_type=CaptureType.RadioHound,
    )
    same_scan_group_caps = [
        capture for capture in captures if str(capture.scan_group) == str(scan_group)
    ]
    if not same_scan_group_caps:
        log.debug("No captures to delete")
        return
    log.warning(
        f"Deleting {len(same_scan_group_caps)} captures with scan group '{scan_group}'"
    )
    for capture in same_scan_group_caps:
        log.warning(f"Deleting capture: {capture.uuid}")
        assert capture.uuid is not None, "Capture UUID should not be None"
        integration_client.captures.delete(capture_uuid=capture.uuid)


def __clean_all_captures(integration_client: Client) -> None:
    """Helper to delete all captures of this user in the SDS."""
    captures = integration_client.captures.listing()
    log.error(len(captures))
    for cap in captures:
        if cap.uuid is None:
            continue
        integration_client.captures.delete(capture_uuid=cap.uuid)
