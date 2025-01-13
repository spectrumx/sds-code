"""Integration tests for file operations on SDS."""

import re
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.ops.files import construct_file, get_valid_files, is_valid_file
from spectrumx.utils import get_random_line

from tests.integration.conftest import passthru_hostnames

BLAKE3_HEX_LEN: int = 64
uuid_v4_regex = (
    r"[0-9a-fA-F]{{8}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]"
    r"{{4}}-[0-9a-fA-F]{{4}}-[0-9a-fA-F]{{12}}"
)


def test_is_valid_file_allowed(temp_file_with_text_contents) -> None:
    """Test the file validation function."""
    allowed_mime_types = [
        "application/json",
        "application/pdf",
        "application/x-hdf5",
        "application/xml",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/svg+xml",
        "text/csv",
        "text/plain",
    ]
    # mock get_file_media_type
    for mime_type in allowed_mime_types:
        with patch("spectrumx.ops.files.get_file_media_type", return_value=mime_type):
            is_valid, reasons = is_valid_file(temp_file_with_text_contents)
            assert is_valid, f"File with MIME type {mime_type} should be allowed."
            assert reasons == [], "No reasons should be given for valid files."


def test_is_valid_file_disallowed(temp_file_with_text_contents) -> None:
    """Test the file validation function."""
    disallowed_mime_types = [
        "application/octet-stream",  # generic binary
        "application/x-msdownload",  # .exe
        "application/x-msdos-program",  # .com
        "application/x-msi",  # .msi
    ]
    # mock get_file_media_type
    for mime_type in disallowed_mime_types:
        with patch("spectrumx.ops.files.get_file_media_type", return_value=mime_type):
            is_valid, reasons = is_valid_file(temp_file_with_text_contents)
            assert (
                not is_valid
            ), f"File with MIME type {mime_type} should be disallowed."
            assert reasons, "Reasons should be given for disallowed files."


def test_get_valid_files(temp_file_tree: Path) -> None:
    """Test get_valid_files yields files matching glob."""

    all_file_paths = {path for path in temp_file_tree.rglob("*") if path.is_file()}
    assert all_file_paths, "No files found: can't run test."
    valid_file_instances = list(get_valid_files(temp_file_tree, warn_skipped=True))
    assert valid_file_instances, "No valid files found."

    # normalize paths to be relative to the temp_file_tree
    valid_file_paths = {
        Path(f"{temp_file_tree}/{file_instance.path}")
        for file_instance in valid_file_instances
    }

    # all test files should be valid and match the local path
    invalid_file_paths = all_file_paths - valid_file_paths
    assert (
        invalid_file_paths == set()
    ), f"All files should be valid. Invalid paths: {invalid_file_paths}"


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
def test_upload_single_file(
    integration_client: Client, temp_file_with_text_contents: Path
) -> None:
    """Test file upload to SDS."""
    sds_path = Path("/")
    local_file = construct_file(temp_file_with_text_contents, sds_path=sds_path)
    uploaded_file = integration_client.upload_file(
        file_path=temp_file_with_text_contents, sds_path=sds_path
    )
    assert uploaded_file.is_sample is False, "Sample file returned."
    for attr in uploaded_file.__dict__:
        log.debug(f"\t{attr:>15} = {uploaded_file.__dict__[attr]}")
    assert uploaded_file is not None, "File upload failed."
    assert isinstance(uploaded_file.uuid, uuid.UUID), "UUID not set."
    assert uploaded_file.size == local_file.size, "Size mismatch."
    assert (
        len(uploaded_file.compute_sum_blake3() or "") == BLAKE3_HEX_LEN
    ), "Checksum not set."
    assert (
        uploaded_file.compute_sum_blake3() == local_file.compute_sum_blake3()
    ), "Checksum mismatch."


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
def test_upload_files_in_bulk(integration_client: Client, temp_file_tree: Path) -> None:
    """Tests uploading multiple files to SDS."""
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
def test_upload_large_file(
    integration_client: Client,
    temp_large_binary_file: Path,
) -> None:
    """Tests uploading a large file to SDS."""
    sds_path = Path("/")
    local_file = construct_file(temp_large_binary_file, sds_path=sds_path)
    uploaded_file = integration_client.upload_file(
        file_path=temp_large_binary_file, sds_path=sds_path
    )
    assert uploaded_file.is_sample is False, "Sample file returned."
    assert uploaded_file is not None, "File upload failed."
    assert isinstance(uploaded_file.uuid, uuid.UUID), "UUID not set."
    assert uploaded_file.size == local_file.size, "Size mismatch."
    assert (
        len(uploaded_file.compute_sum_blake3() or "") == BLAKE3_HEX_LEN
    ), "Checksum not set."
    assert (
        uploaded_file.compute_sum_blake3() == local_file.compute_sum_blake3()
    ), "Checksum mismatch."


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
def test_check_file_content_non_existing(
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
def test_check_file_content_identical(
    integration_client: Client,
    temp_file_with_text_contents: Path,
) -> None:
    """The file content checker must indicate when files are identical."""
    random_string = get_random_line(10, include_punctuation=False)
    sds_path = Path("/") / random_string
    file_instance = construct_file(temp_file_with_text_contents, sds_path=sds_path)

    # upload the file to sds
    uploaded_file = integration_client.upload_file(
        file_path=temp_file_with_text_contents, sds_path=sds_path
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
def test_check_file_content_name_changed(
    integration_client: Client,
    temp_file_with_text_contents: Path,
) -> None:
    """The file content checker must indicate when file names have changed."""
    random_string = get_random_line(10, include_punctuation=False)
    sds_path = Path("/") / random_string

    # upload the file to sds
    uploaded_file = integration_client.upload_file(
        file_path=temp_file_with_text_contents, sds_path=sds_path
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


# TODO:
# def test_file_upload_mode_skip(
# def test_file_upload_mode_contents_and_metadata(
# def test_file_upload_mode_metadata_only(


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            *[  # file metadata download
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
                for hostname_and_port in passthru_hostnames
            ],
            *[  # file metadata download
                re.compile(
                    rf"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files/{uuid_v4_regex}/download"
                )
                for hostname_and_port in passthru_hostnames
            ],
            *[  # file content checks for upload before download
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/utils/check_contents_exist"
                for hostname_and_port in passthru_hostnames
            ],
            *[  # file upload before download
                f"{hostname_and_port}/api/{API_TARGET_VERSION}/assets/files"
                for hostname_and_port in passthru_hostnames
            ],
        ]
    ],
    indirect=True,
)
def test_download_single_file(
    integration_client: Client, temp_file_with_text_contents: Path, tmp_path: Path
) -> None:
    """Test file download from SDS."""
    sds_path = Path("/")

    # upload a test file
    uploaded_file = integration_client.upload_file(
        file_path=temp_file_with_text_contents,
        sds_path=sds_path,
    )
    if uploaded_file is None or uploaded_file.uuid is None:
        pytest.fail("File upload failed.")

    # download that file to a different location
    download_path = tmp_path / "downloaded_file"

    try:
        downloaded_file = integration_client.download_file(
            file_uuid=uploaded_file.uuid, to_local_path=download_path
        )
        downloaded_file.is_same_contents(uploaded_file)

    # cleanup
    finally:
        download_path.unlink(missing_ok=True)


def test_download_files_in_bulk() -> None:
    """Test downloading multiple files from SDS."""
