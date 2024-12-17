"""Integration tests for file operations on SDS."""

import time
import uuid
from pathlib import Path

import pytest
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.ops.files import construct_file
from spectrumx.utils import get_random_line

from tests.integration.conftest import passthru_hostnames

BLAKE3_HEX_LEN: int = 64


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
            for hostname_and_port in passthru_hostnames
        ]
    ],
    indirect=True,
)
def test_single_file_upload(
    integration_client: Client, temp_file_with_text_contents: Path
) -> None:
    """Test file upload to SDS."""
    sds_path = Path("/")
    local_file = construct_file(temp_file_with_text_contents, sds_path=sds_path)
    uploaded_file = integration_client.upload_file(
        temp_file_with_text_contents, sds_path=sds_path
    )
    assert uploaded_file.is_sample is False, "Sample file returned."
    for attr in uploaded_file.__dict__:
        log.debug(f"\t{attr:>15} = {uploaded_file.__dict__[attr]}")
    assert uploaded_file is not None, "File upload failed."
    assert isinstance(uploaded_file.uuid, uuid.UUID), "UUID not set."
    assert uploaded_file.size == local_file.size, "Size mismatch."
    assert len(uploaded_file.sum_blake3 or "") == BLAKE3_HEX_LEN, "Checksum not set."
    assert uploaded_file.sum_blake3 == local_file.sum_blake3, "Checksum mismatch."


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
            for hostname_and_port in passthru_hostnames
        ]
    ],
    indirect=True,
)
def test_bulk_file_upload(integration_client: Client, temp_file_tree: Path) -> None:
    """Test file upload to SDS."""
    random_subdir_name = get_random_line(10, include_punctuation=False)
    results = integration_client.upload(
        local_path=temp_file_tree,
        sds_path=Path("/test-tree") / random_subdir_name,
        verbose=True,
    )
    log.info(f"Uploaded {len(results)} files.")
    for upload_result in results:
        if upload_result:
            continue
        pytest.fail(f"File upload failed: {upload_result}")


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
            for hostname_and_port in passthru_hostnames
        ]
    ],
    indirect=True,
)
@pytest.mark.parametrize(
    "temp_large_binary_file",
    [
        {"size_mb": 10},  # 10 MB
        {"size_mb": 100},  # 100 MB
        # {"size_mb": 1_000},  # 1 GB       # noqa: ERA001
        # {"size_mb": 10_000},  # 10 GB     # noqa: ERA001
    ],
    indirect=True,
)
def test_large_file_upload(
    integration_client: Client,
    temp_large_binary_file: Path,
) -> None:
    """Tests uploading a large file to SDS."""
    sds_path = Path("/")
    local_file = construct_file(temp_large_binary_file, sds_path=sds_path)
    uploaded_file = integration_client.upload_file(
        temp_large_binary_file, sds_path=sds_path
    )
    assert uploaded_file.is_sample is False, "Sample file returned."
    assert uploaded_file is not None, "File upload failed."
    assert isinstance(uploaded_file.uuid, uuid.UUID), "UUID not set."
    assert uploaded_file.size == local_file.size, "Size mismatch."
    assert len(uploaded_file.sum_blake3 or "") == BLAKE3_HEX_LEN, "Checksum not set."
    assert uploaded_file.sum_blake3 == local_file.sum_blake3, "Checksum mismatch."


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/utils/check_contents_exist"
            for hostname_and_port in passthru_hostnames
        ]
    ],
    indirect=True,
)
@pytest.mark.parametrize(
    "temp_large_binary_file",
    [
        {"size_mb": 1},
    ],
    indirect=True,
)
def test_file_content_check_non_existing(
    integration_client: Client,
    temp_large_binary_file: Path,
) -> None:
    """The file content checker must indicate new files don't exist in SDS."""
    file_instance = construct_file(temp_large_binary_file, sds_path=Path("./"))
    file_contents_check = integration_client._gateway.check_file_contents_exist(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        file_instance
    )
    assert (
        file_contents_check.file_contents_exist_for_user is False
    ), "Test file shouldn't exist for user."
    assert (
        file_contents_check.file_exists_in_tree is False
    ), "Test file shouldn't exist in tree."
    assert (
        file_contents_check.user_mutable_attributes_differ is True
    ), "Attributes should always differ for non-existent files."
    assert (
        file_contents_check.asset_id is None
    ), "Asset ID should be None for non-existent files."


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            *[  # file content checks
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/utils/check_contents_exist"
                for hostname_and_port in passthru_hostnames
            ],
            *[  # file uploads
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
                for hostname_and_port in passthru_hostnames
            ],
        ]
    ],
    indirect=True,
)
def test_file_content_check_identical(
    integration_client: Client,
    temp_file_with_text_contents: Path,
) -> None:
    """The file content checker must indicate when files are identical."""
    random_string = get_random_line(10, include_punctuation=False)
    sds_path = Path("/") / random_string
    file_instance = construct_file(temp_file_with_text_contents, sds_path=sds_path)

    # upload the file to sds
    uploaded_file = integration_client.upload_file(
        temp_file_with_text_contents, sds_path=sds_path
    )
    assert uploaded_file.uuid is not None, "UUID not set."
    # sleep
    time.sleep(2)

    file_contents_check = integration_client._gateway.check_file_contents_exist(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        file_instance
    )
    assert (
        file_contents_check.file_contents_exist_for_user is True
    ), "Test file should exist for user."
    assert (
        file_contents_check.file_exists_in_tree is True
    ), "Test file should exist in tree."
    assert (
        file_contents_check.user_mutable_attributes_differ is False
    ), "Attributes should be identical."
    assert file_contents_check.asset_id == str(uploaded_file.uuid), (
        "Asset ID does not match uploaded file: "
        f"{file_contents_check.asset_id} != {uploaded_file.uuid!s}"
    )


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            *[  # file content checks
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/utils/check_contents_exist"
                for hostname_and_port in passthru_hostnames
            ],
            *[  # file uploads
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
                for hostname_and_port in passthru_hostnames
            ],
        ]
    ],
    indirect=True,
)
def test_file_content_check_name_changed(
    integration_client: Client,
    temp_file_with_text_contents: Path,
) -> None:
    """The file content checker must indicate when file names have changed."""
    random_string = get_random_line(10, include_punctuation=False)
    sds_path = Path("/") / random_string

    # upload the file to sds
    uploaded_file = integration_client.upload_file(
        temp_file_with_text_contents, sds_path=sds_path
    )
    assert uploaded_file.uuid is not None, "UUID not set."

    # rename the file
    new_file_name = get_random_line(10, include_punctuation=False)
    new_file_path = temp_file_with_text_contents.with_name(new_file_name)
    assert new_file_path != temp_file_with_text_contents, "File name should change."
    Path.rename(
        temp_file_with_text_contents,
        new_file_path,
    )
    file_instance_renamed = construct_file(new_file_path, sds_path=sds_path)

    file_contents_check = integration_client._gateway.check_file_contents_exist(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
        file_instance_renamed
    )
    assert (
        file_contents_check.file_exists_in_tree is False
    ), "Test file shouldn't be identical to the one in SDS anymore."
    assert (
        file_contents_check.file_contents_exist_for_user is True
    ), "Test file contents should exist for this user, under a different name."
    assert (
        file_contents_check.user_mutable_attributes_differ is True
    ), "Attributes are different (name)."
    assert file_contents_check.asset_id == str(uploaded_file.uuid), (
        "Expected asset ID to be the closest match (sibling UUID) to the uploaded file:"
        f"{file_contents_check.asset_id} != {uploaded_file.uuid!s}"
    )


# def test_file_upload_mode_skip(
# def test_file_upload_mode_contents_and_metadata(
# def test_file_upload_mode_metadata_only(
