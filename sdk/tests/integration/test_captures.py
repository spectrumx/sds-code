"""Tests for SDS Captures."""

import json
from collections.abc import Generator
from pathlib import Path
from pathlib import PurePosixPath

import pytest
from loguru import logger as log
from pydantic import BaseModel
from spectrumx.client import Client
from spectrumx.errors import CaptureError
from spectrumx.models.captures import CaptureType
from spectrumx.utils import get_random_line

from tests.integration.conftest import PassthruEndpoints

log.trace("Placeholder log avoid reimporting or resolving unused import warnings.")

# paths with test data
dir_integration_data = Path(__file__).parent / "data"
dir_local_drf_top_level = dir_integration_data / "captures" / "drf" / "westford-vpol"
drf_channel = "cap-2024-06-27T14-00-00"


@pytest.fixture
def _capture_test() -> Generator[None]:
    """Choose to run capture test or not, based on existing data."""
    if not dir_local_drf_top_level.exists():
        pytest.skip(
            "Capture test SKIPPED. Test data does not "
            f"exist at: '{dir_local_drf_top_level}'"
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
def test_capture_creation_drf(integration_client: Client) -> None:
    """Tests creating a Digital-RF capture."""

    # ARRANGE
    cap_data = _upload_drf_capture_test_assets(integration_client)

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


def _upload_drf_capture_test_assets(integration_client: Client) -> DRFCaptureAssets:
    """Helper to package and upload Digital-RF capture assets to SDS."""
    cap_start_bound: int = 1_719_499_740
    cap_is_continuous: bool = True
    cap_serial: str = "31649FE"

    # define paths in the context of a capture
    dir_top_level = dir_local_drf_top_level
    dir_channel = dir_top_level / drf_channel
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
def test_capture_creation_rh(integration_client: Client) -> None:
    """Tests creating a RadioHound capture."""

    # ARRANGE

    # define paths in the context of a capture
    dir_top_level = dir_integration_data / "captures" / "radiohound"
    radiohound_file = dir_top_level / "reference-v0.rh.json"
    assert radiohound_file.is_file(), (
        "Reference file should exist; check that "
        f"you have the right paths set: '{radiohound_file}'"
    )

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    rel_path_capture = dir_top_level.relative_to(dir_integration_data)
    random_suffix = get_random_line(10, include_punctuation=False)
    rel_path_capture = PurePosixPath(rel_path_capture) / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=rel_path_capture,
        local_path=dir_top_level,
    )

    # ACT

    with radiohound_file.open("r") as fp_json:
        radiohound_data = json.load(fp_json)
    scan_group = radiohound_data["scan_group"]

    # delete all captures with that scan group to avoid conflicts
    _delete_rh_captures_by_scan_group(
        integration_client=integration_client,
        scan_group=scan_group,
    )

    # create a capture
    capture_top_level = PurePosixPath("/") / rel_path_capture
    capture = integration_client.captures.create(
        top_level_dir=capture_top_level,
        scan_group=radiohound_data["scan_group"],
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
        ]
    ],
    indirect=True,
)
def test_capture_listing_all(integration_client: Client) -> None:
    """Tests reading and listing all types of captures."""
    captures = integration_client.captures.listing()
    assert len(captures) > 0, "At least one capture should be present"
    for capture in captures:
        assert capture.uuid is not None, "Capture UUID should not be None"
        assert capture.capture_type in CaptureType.__members__.values(), (
            "Capture type should be one of the known types: "
            f"{CaptureType.__members__.values()}"
        )
        assert capture.top_level_dir is not None, "Top level dir should not be None"


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
def test_capture_update_rh(integration_client: Client) -> None:
    """Tests updating a RadioHound capture."""

    # ARRANGE

    # define paths in the context of a capture
    dir_top_level = dir_integration_data / "captures" / "radiohound"
    radiohound_file = dir_top_level / "reference-v0.rh.json"
    assert radiohound_file.is_file(), (
        "Reference file should exist; check that "
        f"you have the right paths set: '{radiohound_file}'"
    )

    # suffix path_after_capture_data with a random name to avoid conflicts between runs
    rh_capture_update_sds_path = dir_top_level.relative_to(dir_integration_data)
    random_suffix = get_random_line(10, include_punctuation=False)
    rh_capture_update_sds_path = (
        PurePosixPath(rh_capture_update_sds_path) / f"test-{random_suffix}"
    )

    _upload_assets(
        integration_client=integration_client,
        sds_path=rh_capture_update_sds_path,
        local_path=dir_top_level,
    )

    with radiohound_file.open("r") as fp_json:
        radiohound_data = json.load(fp_json)

    scan_group = radiohound_data["scan_group"]

    # delete all captures with that scan group to avoid conflicts
    _delete_rh_captures_by_scan_group(
        integration_client=integration_client,
        scan_group=scan_group,
    )

    # create a capture
    capture_top_level = PurePosixPath("/") / rh_capture_update_sds_path
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

    # ACT

    # update the capture
    integration_client.captures.update(
        capture_uuid=capture.uuid,
    )

    # ASSERT

    # if no exceptions occurred, the test passes
    assert True


def _delete_rh_captures_by_scan_group(
    integration_client: Client, scan_group: str
) -> None:
    """Helper to delete all RadioHound captures with a specific scan group."""
    captures = integration_client.captures.listing(
        capture_type=CaptureType.RadioHound,
    )
    same_scan_group_caps = [
        capture for capture in captures if str(capture.scan_group) == scan_group
    ]
    if not same_scan_group_caps:
        log.debug("No captures to delete")
        return
    log.warning(
        f"Deleting {len(same_scan_group_caps)} captures with scan group '{scan_group}'"
    )
    for capture in same_scan_group_caps:
        log.warning(f"Deleting capture: {capture.uuid}")
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
            *PassthruEndpoints.capture_reading(),
        ]
    ],
    indirect=True,
)
def test_capture_reading_drf(integration_client: Client) -> None:
    """Tests reading a specific Digital-RF capture."""

    # ARRANGE

    # define paths in the context of a capture
    dir_top_level = dir_local_drf_top_level
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

    # create a capture
    capture = integration_client.captures.create(
        top_level_dir=Path(f"/{path_after_capture_data}"),
        channel=drf_channel,
        capture_type=CaptureType.DigitalRF,
    )

    # ACT

    # read the capture
    read_capture = integration_client.captures.read(
        capture_uuid=capture.uuid,
    )

    # ASSERT

    # basic capture information
    log.error(f"{read_capture!s}")
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
def test_capture_deletion(integration_client: Client) -> None:
    """Tests deleting a capture."""

    # ARRANGE
    # create capture contents on SDS
    cap_data = _upload_drf_capture_test_assets(integration_client)

    # create a capture to delete
    capture = integration_client.captures.create(
        top_level_dir=cap_data.capture_top_level,
        capture_type=CaptureType.DigitalRF,
        channel=cap_data.drf_channel,
    )

    # ACT
    result = integration_client.captures.delete(capture_uuid=capture.uuid)

    # ASSERT
    assert result is True, "Capture deletion should return True"
    with pytest.raises(CaptureError):
        integration_client.captures.read(
            capture_uuid=capture.uuid,
        )


def _upload_assets(
    integration_client: Client,
    sds_path: Path | PurePosixPath,
    local_path: Path,
) -> None:
    """Helper to upload a local directory to SDS and assert success."""
    log.debug(f"Uploading assets as '/{sds_path}'")
    upload_results = integration_client.upload(
        local_path=local_path,
        sds_path=f"/{sds_path}",
        verbose=False,
    )
    success_results = [success for success in upload_results if success]
    failed_results = [success for success in upload_results if not success]
    assert len(failed_results) == 0, (
        f"No failed uploads should be present: {failed_results}"
    )
    log.debug(f"Uploaded {len(success_results)} assets.")
