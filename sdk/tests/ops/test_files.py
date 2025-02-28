"""Tests file operations."""
# pylint: disable=redefined-outer-name

import json
import tempfile
import uuid as uuidlib
from datetime import datetime
from pathlib import Path

from responses import RequestsMock
from spectrumx import Client
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.ops.files import get_file_permissions

from tests.conftest import get_files_endpoint


def _download_file_endpoint(client: Client, file_id: str) -> str:
    """Returns the endpoint for downloading a file."""
    return (
        client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/{file_id}/download/"
    )


def _get_file_id_endpoint(client: Client, file_id: str) -> str:
    """Returns the endpoint for getting a file."""
    return client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/{file_id}/"


def _get_content_check_endpoint(client: Client) -> str:
    """Returns the endpoint for the content check API."""
    return (
        client.base_url
        + f"/api/{API_TARGET_VERSION}/assets/utils/check_contents_exist/"
    )


def test_get_file_permissions(temp_file_empty: Path) -> None:
    """Test get_file_permissions for many permission combinations."""
    chmod_combos = {
        "---------": 0o000,
        "--------x": 0o001,
        "r-xr-xr--": 0o554,
        "r--rw-r--": 0o464,
        "rw-rw-r--": 0o664,
        "rwx------": 0o700,
        "rwxrwxrwx": 0o777,
    }
    for perm_string, chmod in chmod_combos.items():
        temp_file_empty.chmod(chmod)
        assert get_file_permissions(temp_file_empty) == perm_string


def test_get_file_by_id(client: Client, responses: RequestsMock) -> None:
    """Given a file ID, the client must return the file."""
    uuid = uuidlib.uuid4()
    url: str = get_files_endpoint(client) + f"{uuid.hex}/"
    responses.get(
        url=url,
        status=200,
        json={
            "created_at": "2021-10-01T12:00:00Z",
            "directory": "/my/files/are/here/",
            "expiration_date": "2021-10-01T12:12:00Z",
            "media_type": "text/plain",
            "name": "file.txt",
            "permissions": "rw-rw-r--",
            "size": 321,
            "updated_at": "2021-10-01T12:00:00Z",
            "uuid": uuid.hex,
        },
    )
    client.dry_run = False  # to test the actual request
    file_sample = client.get_file(file_uuid=uuid.hex)
    assert file_sample.uuid == uuid


def test_file_get_returns_valid(
    client: Client,
) -> None:
    """The get_file method must return a valid File instance.

    Note the file may not exist locally, but the File instance can still be valid.
        That is the case for dry-runs - which use sample files - and for files fetched
        from the server that have not yet been downloaded.
    """

    file_id = uuidlib.uuid4()
    file_size = 888
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    file_sample = client.get_file(file_uuid=file_id.hex)
    assert file_sample.is_sample is True, "The file must be a sample file"  # pyright: ignore[reportPrivateUsage]
    assert file_sample.uuid is not None
    assert file_sample.name.startswith("dry-run-")
    assert file_sample.media_type == "text/plain"
    assert file_sample.size == file_size
    assert file_sample.directory == Path("sds-files/dry-run/")
    assert file_sample.permissions == "rw-rw-r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert isinstance(file_sample.expiration_date, datetime), (
        "Expiration date should be a datetime"
    )
    assert file_sample.expiration_date > file_sample.created_at


def test_file_upload_returns_file(
    client: Client, temp_file_with_text_contents: Path
) -> None:
    """The upload_file method must return a valid File instance."""
    test_file_size = temp_file_with_text_contents.stat().st_size
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    file_sample = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=Path("/my/upload/location"),
    )
    assert file_sample.is_sample is False, (
        "The file must be a real file on disk (not a sample), even for this test"
    )  # pyright: ignore[reportPrivateUsage]
    assert temp_file_with_text_contents == file_sample.local_path, (
        "Local path does not match"
    )
    assert file_sample.uuid is None, "A local file must not have a UUID"
    assert file_sample.name is not None, "Expected a file name"
    assert file_sample.media_type == "text/plain", "Expected media type 'text/plain'"
    assert file_sample.size == test_file_size, "Expected the test file to be 4030 bytes"
    assert "/tmp/pytest-" in str(  # noqa: S108
        file_sample.local_path
    ), "Expected the temp file directory"
    assert file_sample.directory == Path("/my/upload/location")
    assert file_sample.permissions == "rw-r--r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert file_sample.expiration_date is None, (
        "Local files should not have an expiration date"
    )


def test_large_file_upload_mocked(
    client: Client, responses: RequestsMock, temp_large_binary_file: Path
) -> None:
    """Test the upload_file method with mocked responses."""
    file_id = uuidlib.uuid4()
    file_size = temp_large_binary_file.stat().st_size
    client.dry_run = False  # calls are mocked, but we want to test the actual requests
    mocked_file_content_check_json = {
        "file_contents_exist_for_user": False,
        "file_exists_in_tree": False,
        "user_mutable_attributes_differ": True,
    }
    responses.add(
        method=responses.POST,
        url=_get_content_check_endpoint(client),
        status=201,
        json=mocked_file_content_check_json,
    )
    mocked_upload_json = {
        "uuid": file_id.hex,
        "name": temp_large_binary_file.name,
        "media_type": "text/plain",
        "size": file_size,
        "directory": "/my/custom/sds/location",
        "permissions": "rw-r--r--",
        "created_at": "2024-12-01T12:00:00Z",
        "updated_at": "2024-12-01T12:00:00Z",
        "expiration_date": "2026-12-01T12:00:00Z",
    }
    responses.add(
        method=responses.POST,
        url=get_files_endpoint(client),
        status=201,
        json=mocked_upload_json,
    )
    # run the test
    file_sample = client.upload_file(
        local_file=temp_large_binary_file,
        sds_path=Path(mocked_upload_json["directory"]),
    )
    assert file_sample.uuid == file_id, "UUID not as mocked."
    assert file_sample.name == mocked_upload_json["name"]
    assert file_sample.media_type == mocked_upload_json["media_type"]
    assert file_sample.size == file_size
    assert file_sample.directory == Path(mocked_upload_json["directory"])
    assert file_sample.permissions == mocked_upload_json["permissions"]
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)


def test_download_file_contents(client: Client, responses: RequestsMock) -> None:
    """The download_file_contents method must create a file with the file contents."""
    client.dry_run = False  # calls are mocked, but we want to test the actual requests

    # file properties
    file_id = uuidlib.uuid4()
    long_file_contents = (
        "File start\n" + "Sample file contents - " * 1000 + "\nFile end"
    )
    num_bytes = len(long_file_contents.encode("utf-8"))

    file_metadata = {
        "uuid": file_id.hex,
        "name": "downloaded-file.txt",
        "media_type": "text/plain",
        "size": num_bytes,
        "directory": "/my/download/location",
        "permissions": "rw-r--r--",
        "created_at": "2024-12-01T12:00:00Z",
        "updated_at": "2024-12-01T12:00:00Z",
        "expiration_date": "2026-12-01T12:00:00Z",
    }

    # mock the file metadata endpoint
    responses.add(
        method=responses.GET,
        url=_get_file_id_endpoint(client, file_id=file_id.hex),
        status=200,
        body=json.dumps(file_metadata),
    )

    # mock the file download endpoint
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=200,
        body=long_file_contents,
    )

    # run the test
    downloaded_file = client.download_file(file_uuid=file_id.hex)
    downloaded_path = downloaded_file.local_path
    assert downloaded_path is not None, "Returned path must not be None"
    assert downloaded_path.exists(), "File was not downloaded to returned path"
    assert downloaded_path.is_file(), "Returned path must be a file"
    assert downloaded_path.stat().st_size == num_bytes, (
        f"File size must match. Got {num_bytes} B, "
        f"expected {downloaded_file.stat().st_size} B"
    )

    # cleanup
    downloaded_path.unlink(missing_ok=False)


def test_download_file_to_path(client: Client, responses: RequestsMock) -> None:
    """The download method must respect the given path, creating any parent dirs."""
    client.dry_run = False  # calls are mocked, but we want to test the actual requests

    # file properties
    file_id = uuidlib.uuid4()
    file_contents = "File start\n" + "Sample file contents" + "\nFile end"
    num_bytes = len(file_contents.encode("utf-8"))
    random_str = uuidlib.uuid4().hex
    parent_dir = Path(tempfile.gettempdir()) / random_str
    expected_path = parent_dir / "downloaded-file.txt"

    # mock the file metadata endpoint
    file_metadata = {
        "uuid": file_id.hex,
        "name": expected_path.name,
        "media_type": "text/plain",
        "size": num_bytes,
        "directory": "/my/download/location",
        "permissions": "rw-r--r--",
        "created_at": "2024-12-01T12:00:00Z",
        "updated_at": "2024-12-01T12:00:00Z",
        "expiration_date": "2026-12-01T12:00:00Z",
    }
    responses.add(
        method=responses.GET,
        url=_get_file_id_endpoint(client, file_id=file_id.hex),
        status=200,
        body=json.dumps(file_metadata),
    )

    # mock the file download endpoint
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=200,
        body=file_contents,
    )

    # run the test
    assert parent_dir.exists() is False, "Parent dir must not exist before test"
    downloaded_file = client.download_file(
        file_uuid=file_id.hex, to_local_path=expected_path
    )
    downloaded_path = downloaded_file.local_path
    assert downloaded_path == expected_path, "Returned path must match the given path"
    assert expected_path.exists(), "File was not downloaded to given path"
    assert expected_path.is_file(), "Given path must be a file"
    assert expected_path.stat().st_size == num_bytes, (
        f"File size must match. Got {num_bytes} B, "
        f"expected {expected_path.stat().st_size} B"
    )

    # cleanup
    expected_path.unlink(missing_ok=False)
    parent_dir.rmdir()
