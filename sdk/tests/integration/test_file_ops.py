"""Integration tests for file operations on SDS."""

import uuid
from pathlib import Path

import pytest
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.ops.files import construct_file
from spectrumx.utils import get_random_line

BLAKE3_HEX_LEN: int = 64


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    [
        [
            f"https://sds.crc.nd.edu:443/api/{API_TARGET_VERSION}/assets/files",
            f"http://localhost:80/api/{API_TARGET_VERSION}/assets/files",
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
            f"https://sds.crc.nd.edu:443/api/{API_TARGET_VERSION}/assets/files",
            f"http://localhost:80/api/{API_TARGET_VERSION}/assets/files",
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
            f"https://sds.crc.nd.edu:443/api/{API_TARGET_VERSION}/assets/files",
            f"http://localhost:80/api/{API_TARGET_VERSION}/assets/files",
        ]
    ],
    indirect=True,
)
def test_large_file_upload(
    integration_client: Client, temp_large_binary_file: Path
) -> None:
    """Tests uploading a large file to SDS."""
    sds_path = Path("/")
    local_file = construct_file(temp_large_binary_file, sds_path=sds_path)
    uploaded_file = integration_client.upload_file(
        temp_large_binary_file, sds_path=sds_path
    )
    assert uploaded_file.is_sample is False, "Sample file returned."
    for attr in uploaded_file.__dict__:
        log.debug(f"\t{attr:>15} = {uploaded_file.__dict__[attr]}")
    assert uploaded_file is not None, "File upload failed."
    assert isinstance(uploaded_file.uuid, uuid.UUID), "UUID not set."
    assert uploaded_file.size == local_file.size, "Size mismatch."
    assert len(uploaded_file.sum_blake3 or "") == BLAKE3_HEX_LEN, "Checksum not set."
    assert uploaded_file.sum_blake3 == local_file.sum_blake3, "Checksum mismatch."
