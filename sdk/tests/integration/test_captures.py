"""Tests for SDS Captures."""

import json
from collections.abc import Generator
from pathlib import Path

import pytest
from loguru import logger as log
from spectrumx.client import Client
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

    # metadata in this digital-rf capture in test data
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
    path_after_capture_data = path_after_capture_data / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=path_after_capture_data,
        local_path=dir_top_level,
    )

    # ACT

    # create a capture
    capture = integration_client.captures.create(
        top_level_dir=Path(f"/{path_after_capture_data}"),
        channel=drf_channel,
        capture_type=CaptureType.DigitalRF,
    )

    # ASSERT

    # basic capture information
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.DigitalRF
    assert capture.channel == drf_channel
    assert capture.top_level_dir == Path(f"/{path_after_capture_data}")

    # test capture properties
    assert capture.capture_props["start_bound"] == cap_start_bound
    assert capture.capture_props["is_continuous"] == cap_is_continuous
    assert (
        capture.capture_props["custom_attrs"]["receiver/info/mboard_serial"]
        == cap_serial
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
    rel_path_capture = rel_path_capture / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=rel_path_capture,
        local_path=dir_top_level,
    )

    # ACT

    with radiohound_file.open("r") as fp_json:
        radiohound_data = json.load(fp_json)

    log.error(radiohound_data["scan_group"])

    # create a capture
    capture = integration_client.captures.create(
        top_level_dir=rel_path_capture,
        scan_group=radiohound_data["scan_group"],
        capture_type=CaptureType.RadioHound,
    )

    # ASSERT

    # basic capture information
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.RadioHound
    assert capture.top_level_dir == rel_path_capture

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
    """Tests reading and listing a Digital-RF capture."""
    captures = integration_client.captures.listing(
        capture_type=CaptureType.DigitalRF,
    )
    assert len(captures) > 0, "At least one capture should be present"
    for capture in captures:
        assert capture.uuid is not None, "Capture UUID should not be None"
        assert capture.capture_type == CaptureType.DigitalRF
        assert capture.channel is not None
        assert capture.top_level_dir is not None


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
    rh_capture_update_sds_path = rh_capture_update_sds_path / f"test-{random_suffix}"

    _upload_assets(
        integration_client=integration_client,
        sds_path=rh_capture_update_sds_path,
        local_path=dir_top_level,
    )

    with radiohound_file.open("r") as fp_json:
        radiohound_data = json.load(fp_json)

    # create a capture
    capture = integration_client.captures.create(
        top_level_dir=Path(f"/{rh_capture_update_sds_path}"),
        scan_group=radiohound_data["scan_group"],
        capture_type=CaptureType.RadioHound,
    )

    # ASSERT

    # basic capture information
    assert capture.uuid is not None, "Capture UUID should not be None"
    assert capture.capture_type == CaptureType.RadioHound
    assert capture.top_level_dir == Path(f"/{rh_capture_update_sds_path}")

    # test capture metadata
    assert capture.capture_props, "Capture properties should not be empty"
    assert capture.capture_props == radiohound_data, (
        "Capture props doesn't match the reference data: \n"
        f"'{capture.capture_props}'\n!=\n'{radiohound_data}'"
    )

    # upload a new radiohound file
    new_radiohound_file = dir_top_level / "reference-v0-addendum.rh.json"
    assert new_radiohound_file.is_file(), (
        "New reference file should exist; check that "
        f"you have the right paths set: '{new_radiohound_file}'"
    )

    _upload_assets(
        integration_client=integration_client,
        sds_path=rh_capture_update_sds_path,
        local_path=dir_top_level,
    )

    # ACT

    # update the capture
    integration_client.captures.update(
        capture_uuid=capture.uuid,
    )

    # ASSERT

    # if no exceptions occurred, the test passes
    assert True


def _upload_assets(
    integration_client: Client,
    sds_path: Path,
    local_path: Path,
) -> None:
    """Helper to upload a local directory to SDS and assert success."""
    log.info(f"Uploading assets as '/{sds_path}'")
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
