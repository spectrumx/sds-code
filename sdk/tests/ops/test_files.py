"""Tests file operations."""
# pylint: disable=redefined-outer-name

import json
import sys
import tempfile
import uuid as uuidlib
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path
from pathlib import PurePosixPath
from threading import RLock
from unittest.mock import patch

import pytest
import responses
from spectrumx import Client
from spectrumx.api.sds_files import (  # pyright: ignore[reportPrivateUsage]
    __download_file_contents,
)
from spectrumx.api.sds_files import (  # pyright: ignore[reportPrivateUsage]
    __update_existing_file_metadata_only,
)
from spectrumx.api.sds_files import (  # pyright: ignore[reportPrivateUsage]
    __upload_contents_and_metadata,
)
from spectrumx.api.sds_files import (  # pyright: ignore[reportPrivateUsage]
    __upload_new_file_metadata_only,
)
from spectrumx.api.sds_files import delete_file
from spectrumx.api.sds_files import download_file
from spectrumx.api.sds_files import file_list_time_query_param
from spectrumx.api.sds_files import list_files
from spectrumx.api.sds_files import upload_file
from spectrumx.api.uploads import UploadPersistenceManager
from spectrumx.errors import FileError
from spectrumx.errors import SDSError
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.models.files import File
from spectrumx.ops.files import (
    _load_undesired_globs,  # pyright: ignore[reportPrivateUsage]
)
from spectrumx.ops.files import get_file_permissions
from spectrumx.ops.files import is_valid_file

from tests.conftest import get_content_check_endpoint
from tests.conftest import get_file_detach_from_datasets_url
from tests.conftest import get_files_endpoint


def _download_file_endpoint(client: Client, file_id: str) -> str:
    """Returns the endpoint for downloading a file."""
    return (
        client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/{file_id}/download/"
    )


def _get_file_id_endpoint(client: Client, file_id: str) -> str:
    """Returns the endpoint for getting a file."""
    return client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/{file_id}/"


@pytest.mark.linux
@pytest.mark.darwin
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
        assert get_file_permissions(temp_file_empty) == perm_string, (
            f"Expected permissions {perm_string}, got "
            f"{get_file_permissions(temp_file_empty)}"
        )


@pytest.mark.win32
def test_get_file_permissions_win32(temp_file_empty: Path) -> None:
    """
    Test get_file_permissions for many permission combinations.

    Windows only allows setting read or write permissions on a file.
    """
    chmod_combos = {
        "r--r--r--": 0o400,
        "r--r--r--": 0o440,  # noqa: F601
        "r--r--r--": 0o444,  # noqa: F601
        "rw-rw-rw-": 0o600,
        "rw-rw-rw-": 0o660,  # noqa: F601
        "rw-rw-rw-": 0o666,  # noqa: F601
    }
    for perm_string, chmod in chmod_combos.items():
        temp_file_empty.chmod(chmod)
        assert get_file_permissions(temp_file_empty) == perm_string, (
            f"Expected permissions {perm_string}, got "
            f"{get_file_permissions(temp_file_empty)}"
        )


def test_get_file_by_id(client: Client, responses: responses.RequestsMock) -> None:
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
    assert file_sample.uuid == uuid, f"Expected UUID {uuid}, got {file_sample.uuid}"


def test_list_files_start_end_must_be_paired(client: Client) -> None:
    """Omitting one of ``start_time`` / ``end_time`` raises before any request."""
    t = datetime(2024, 6, 27, 14, 0, tzinfo=UTC)
    with pytest.raises(ValueError, match="both be set or both omitted"):
        list_files(client=client, sds_path="/", start_time=t, end_time=None)
    with pytest.raises(ValueError, match="both be set or both omitted"):
        list_files(client=client, sds_path="/", start_time=None, end_time=t)


def test_file_list_time_query_param_naive_treated_as_utc() -> None:
    """Naive datetimes are interpreted as UTC for query strings."""
    naive = datetime(2024, 6, 27, 14, 9, 0)  # noqa: DTZ001
    out = file_list_time_query_param(naive)
    assert out.endswith("+00:00")
    assert "2024-06-27T14:09:00" in out


def test_file_list_time_query_param_converts_non_utc_to_utc() -> None:
    """Aware datetimes are formatted in UTC (same instant)."""
    eastern = timezone(timedelta(hours=-5))
    local = datetime(2024, 6, 27, 9, 9, 0, tzinfo=eastern)
    out = file_list_time_query_param(local)
    assert "2024-06-27T14:09:00" in out
    assert out.endswith("+00:00")


def test_list_files_passes_iso_temporal_params_to_gateway(client: Client) -> None:
    """Temporal bounds are forwarded to ``gateway.list_files`` as ISO strings."""
    client.dry_run = False
    start = datetime(2024, 6, 27, 14, 9, 0, tzinfo=UTC)
    end = datetime(2024, 6, 27, 14, 10, 0, tzinfo=UTC)
    expected_start = file_list_time_query_param(start)
    expected_end = file_list_time_query_param(end)
    empty_page = b'{"count": 0, "results": []}'

    with patch.object(
        client.gateway,
        "list_files",
        return_value=empty_page,
    ) as m:
        paginator = list_files(
            client=client,
            sds_path=PurePosixPath("/drf/dir"),
            start_time=start,
            end_time=end,
        )
        list(paginator)

    m.assert_called()
    for call in m.call_args_list:
        kw = call.kwargs
        assert kw["start_time"] == expected_start
        assert kw["end_time"] == expected_end
        assert kw["sds_path"] == PurePosixPath("/drf/dir")


def test_client_download_forwards_temporal_bounds_to_list_files(
    client: Client, tmp_path: Path
) -> None:
    """``Client.download(..., start_time=, end_time=)`` lists with the same bounds."""
    client.dry_run = False
    start = datetime(2024, 6, 27, 14, 9, 0, tzinfo=UTC)
    end = datetime(2024, 6, 27, 14, 11, 0, tzinfo=UTC)
    sds = PurePosixPath("/capture/rf")

    with patch.object(client, "list_files", return_value=[]) as m_list:
        client.download(
            from_sds_path=sds,
            start_time=start,
            end_time=end,
            to_local_path=tmp_path,
            verbose=False,
        )

    m_list.assert_called_once()
    assert m_list.call_args.kwargs["sds_path"] == sds
    assert m_list.call_args.kwargs["start_time"] == start
    assert m_list.call_args.kwargs["end_time"] == end


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
    assert file_sample.uuid is not None, "File UUID should not be None"
    assert file_sample.name.startswith("dry-run-"), (
        f"Expected name to start with 'dry-run-', got '{file_sample.name}'"
    )
    assert file_sample.media_type == "text/plain", (
        f"Expected media_type 'text/plain', got '{file_sample.media_type}'"
    )
    assert file_sample.size == file_size, (
        f"Expected size {file_size}, got {file_sample.size}"
    )
    assert file_sample.directory == PurePosixPath("sds-files/dry-run/"), (
        f"Expected directory 'sds-files/dry-run/', got '{file_sample.directory}'"
    )
    assert file_sample.permissions == "rw-rw-r--", (
        f"Expected permissions 'rw-rw-r--', got '{file_sample.permissions}'"
    )
    assert isinstance(file_sample.created_at, datetime), (
        "created_at should be a datetime"
    )
    assert isinstance(file_sample.updated_at, datetime), (
        "updated_at should be a datetime"
    )
    assert isinstance(file_sample.expiration_date, datetime), (
        "Expiration date should be a datetime"
    )
    assert file_sample.expiration_date > file_sample.created_at, (
        "Expiration date should be after created_at"
    )


def test_file_upload_returns_file(
    client: Client, temp_file_with_text_contents: Path, tmp_path: Path
) -> None:
    """The upload_file method must return a valid File instance."""
    test_file_size = temp_file_with_text_contents.stat().st_size
    client.dry_run = True
    assert client.dry_run is True, "Dry run must be enabled for this test."
    file_sample = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/my/upload/location"),
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
    assert str(tmp_path) in str(file_sample.local_path), (
        "Expected the temp file directory"
    )
    assert file_sample.directory == PurePosixPath("/my/upload/location"), (
        f"Expected directory '/my/upload/location', got '{file_sample.directory}'"
    )
    expected_permissions = "rw-rw-rw-" if sys.platform == "win32" else "rw-r--r--"
    assert file_sample.permissions == expected_permissions, (
        f"Expected permissions '{expected_permissions}', "
        f"got '{file_sample.permissions}'"
    )

    assert isinstance(file_sample.created_at, datetime), (
        "created_at should be a datetime"
    )
    assert isinstance(file_sample.updated_at, datetime), (
        "updated_at should be a datetime"
    )
    assert file_sample.expiration_date is None, (
        "Local files should not have an expiration date"
    )


def test_large_file_upload_mocked(
    client: Client, responses: responses.RequestsMock, temp_large_binary_file: Path
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
        url=get_content_check_endpoint(client),
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
        sds_path=PurePosixPath(mocked_upload_json["directory"]),
    )
    assert file_sample.uuid == file_id, "UUID not as mocked."
    assert file_sample.name == mocked_upload_json["name"], (
        f"Expected name '{mocked_upload_json['name']}', got '{file_sample.name}'"
    )
    assert file_sample.media_type == mocked_upload_json["media_type"], (
        f"Expected media_type '{mocked_upload_json['media_type']}', "
        f"got '{file_sample.media_type}'"
    )
    assert file_sample.size == file_size, (
        f"Expected size {file_size}, got {file_sample.size}"
    )
    assert file_sample.directory == PurePosixPath(mocked_upload_json["directory"]), (
        f"Expected directory '{mocked_upload_json['directory']}', "
        f"got '{file_sample.directory}'"
    )
    assert file_sample.permissions == mocked_upload_json["permissions"], (
        f"Expected permissions '{mocked_upload_json['permissions']}', "
        f"got '{file_sample.permissions}'"
    )
    assert isinstance(file_sample.created_at, datetime), (
        "created_at should be a datetime"
    )
    assert isinstance(file_sample.updated_at, datetime), (
        "updated_at should be a datetime"
    )


def test_download_file_contents(
    client: Client, responses: responses.RequestsMock
) -> None:
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


def test_download_file_to_path(
    client: Client, responses: responses.RequestsMock
) -> None:
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


def test_detach_file_from_datasets_success(
    client: Client, responses: responses.RequestsMock
) -> None:
    """PUT detach-from-datasets uses the dedicated action URL."""
    file_uuid = uuidlib.uuid4()
    client.dry_run = False
    detach_url = get_file_detach_from_datasets_url(client, file_id=file_uuid.hex)
    responses.add(
        responses.PUT,
        detach_url,
        status=200,
        json={
            "message": "File detached from all connected datasets successfully",
        },
    )

    assert client.detach_file_from_datasets(file_uuid=file_uuid) is True, (
        "Expected detach to return True"
    )
    assert len(responses.calls) == 1, (
        f"Expected 1 response call, got {len(responses.calls)}"
    )
    assert responses.calls[0].request.method == "PUT", (
        f"Expected PUT request, got {responses.calls[0].request.method}"
    )
    assert responses.calls[0].request.url == detach_url, (
        f"Expected URL '{detach_url}', got '{responses.calls[0].request.url}'"
    )


def test_detach_file_from_datasets_dry_run(client: Client) -> None:
    """Dry run does not call the gateway."""
    client.dry_run = True
    assert client.detach_file_from_datasets(file_uuid=uuidlib.uuid4()) is True, (
        "Dry-run detach should return True without calling gateway"
    )


def test_delete_file_success(client: Client, responses: responses.RequestsMock) -> None:
    """Test successful file deletion."""
    # ARRANGE
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False
    assert client.dry_run is False, "Dry run must be DISABLED for this test."
    responses.add(
        responses.DELETE,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )
    responses.add(
        responses.GET,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        json={
            "uuid": test_uuid_hex,
            "name": "test_file.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/test/",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )
    num_reqs = 2

    # ACT
    result = delete_file(client=client, file_uuid=test_uuid)

    # ASSERT
    assert result is True, "Expected deletion to succeed."
    assert len(responses.calls) == num_reqs, (
        "Expected one file GET and one DELETE request to be made."
    )
    assert responses.calls[1].request.method == "DELETE", (
        f"Expected DELETE, got {responses.calls[1].request.method}"
    )
    assert (
        responses.calls[1].request.url
        == f"{get_files_endpoint(client)}{test_uuid_hex}/"
    ), (
        f"Expected URL '{get_files_endpoint(client)}{test_uuid_hex}/', "
        f"got '{responses.calls[1].request.url}'"
    )


def test_delete_file_raises_when_gateway_rejects_due_to_datasets_or_sharing(
    client: Client,
    responses: responses.RequestsMock,
) -> None:
    """GET then DELETE: gateway returns 400 when delete is blocked (share/dataset)."""
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False
    file_json = {
        "uuid": test_uuid_hex,
        "name": "test_file.txt",
        "media_type": "text/plain",
        "size": 100,
        "directory": "/test/",
        "permissions": "rw-r--r--",
        "created_at": "2024-12-01T12:00:00Z",
        "updated_at": "2024-12-01T12:00:00Z",
        "expiration_date": "2026-12-01T12:00:00Z",
    }
    err_msg = "Cannot delete file: detach from datasets or revoke shares first."
    responses.add(
        responses.GET,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        json=file_json,
    )
    responses.add(
        responses.DELETE,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=400,
        json={"detail": err_msg},
    )
    num_reqs = 2
    with pytest.raises(FileError) as exc_info:
        delete_file(client=client, file_uuid=test_uuid)
    assert err_msg in str(exc_info.value), (
        f"Expected error message containing '{err_msg}', got '{exc_info.value}'"
    )
    assert len(responses.calls) == num_reqs, (
        f"Expected {num_reqs} calls, got {len(responses.calls)}"
    )
    assert responses.calls[1].request.method == "DELETE", (
        f"Expected DELETE, got {responses.calls[1].request.method}"
    )


def test_delete_file_str_uuid(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Test file deletion with string UUID."""
    # ARRANGE
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False  # calls are mocked, but we want to test the actual requests
    assert client.dry_run is False, "Dry run must be DISABLED for this test."
    responses.add(
        responses.GET,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        json={
            "uuid": test_uuid_hex,
            "name": "test_file.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/test/",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )
    responses.add(
        responses.DELETE,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )
    num_reqs = 2

    # ACT
    result = delete_file(client=client, file_uuid=test_uuid_hex)

    # ASSERT
    assert result is True, "Expected deletion to succeed."
    assert len(responses.calls) == num_reqs, (
        "Expected one file GET and one DELETE request to be made."
    )
    assert responses.calls[1].request.method == "DELETE", (
        f"Expected DELETE, got {responses.calls[1].request.method}"
    )
    assert (
        responses.calls[1].request.url
        == f"{get_files_endpoint(client)}{test_uuid_hex}/"
    ), (
        f"Expected URL '{get_files_endpoint(client)}{test_uuid_hex}/', "
        f"got '{responses.calls[1].request.url}'"
    )


def test_delete_file_dry_run(client: Client, responses: responses.RequestsMock) -> None:
    """Test file deletion in dry run mode."""
    # ARRANGE
    test_uuid = uuidlib.uuid4()
    assert client.dry_run is True, "Dry run must be enabled for this test."

    # ACT
    result = delete_file(client=client, file_uuid=test_uuid)

    # ASSERT
    assert result is True, "Deletion should succeed in dry run mode"
    assert len(responses.calls) == 0, (
        f"Expected 0 calls in dry run, got {len(responses.calls)}"
    )


class TestIsValidFile:
    """Test cases for the is_valid_file function."""

    def test_valid_text_file(self, temp_file_with_text_contents: Path) -> None:
        """Test that a valid text file passes validation."""
        is_valid, reasons = is_valid_file(temp_file_with_text_contents)
        assert is_valid is True, (
            f"Valid text file should pass validation. Reasons: {reasons}"
        )
        assert reasons == [], "No reasons should be given for valid files"

    def test_valid_json_file(self, tmp_path: Path) -> None:
        """Test that a valid JSON file passes validation."""
        json_file = tmp_path / "test.json"
        json_file.write_text('{"test": "data"}')

        is_valid, reasons = is_valid_file(json_file)
        assert is_valid is True, (
            f"Valid JSON file should pass validation. Reasons: {reasons}"
        )
        assert reasons == [], "No reasons should be given for valid files"

    def test_valid_image_file(self, tmp_path: Path) -> None:
        """Test that a valid image file passes validation."""
        # Create a minimal PNG file (1x1 pixel)
        png_data = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00"
            b"\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc```\x00\x00\x00\x04"
            b"\x00\x01\xdd\x8d\xb4\x1c\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        png_file = tmp_path / "test.png"
        png_file.write_bytes(png_data)

        is_valid, reasons = is_valid_file(png_file)
        assert is_valid is True, (
            f"Valid PNG file should pass validation. Reasons: {reasons}"
        )
        assert reasons == [], "No reasons should be given for valid files"

    def test_empty_file(self, tmp_path: Path) -> None:
        """Test that an empty file fails validation."""
        empty_file = tmp_path / "empty.txt"
        empty_file.touch()

        is_valid, reasons = is_valid_file(empty_file)
        assert is_valid is False, "Empty file should fail validation"
        assert "Empty file, or could not read it" in reasons, (
            f"Expected 'Empty file' reason, got: {reasons}"
        )

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Test that a nonexistent file fails validation."""
        nonexistent_file = tmp_path / "nonexistent.txt"

        is_valid, reasons = is_valid_file(nonexistent_file)
        assert is_valid is False, "Nonexistent file should fail validation"
        assert "Not a file" in reasons, f"Expected 'Not a file' reason, got: {reasons}"

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        """Test that a directory fails validation."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        is_valid, reasons = is_valid_file(test_dir)
        assert is_valid is False, "Directory should fail validation"
        assert "Not a file" in reasons, (
            f"Expected 'Not a file' reason for directory, got: {reasons}"
        )

    def test_disallowed_executable_file(self, tmp_path: Path, monkeypatch) -> None:
        """Test that executable files with disallowed MIME types fail validation."""
        # Create a non-empty file so MIME check is exercised (not the empty-file check)
        exe_file = tmp_path / "test.exe"
        exe_file.write_text("dummy content")

        # Patch get_file_media_type to return an application/* MIME for this file
        monkeypatch.setattr(
            "spectrumx.ops.files.get_file_media_type",
            lambda _path: "application/x-msdownload",
        )

        is_valid, reasons = is_valid_file(exe_file)
        assert is_valid is False, "Executable file should fail validation"
        assert any("Invalid MIME type" in reason for reason in reasons), (
            f"Expected 'Invalid MIME type' reason, got: {reasons}"
        )

    def test_disallowed_msi_file(self, tmp_path: Path, monkeypatch) -> None:
        """Test that MSI files fail validation."""
        msi_file = tmp_path / "test.msi"
        msi_file.write_text("dummy content")

        monkeypatch.setattr(
            "spectrumx.ops.files.get_file_media_type",
            lambda _path: "application/x-msi",
        )

        is_valid, reasons = is_valid_file(msi_file)
        assert is_valid is False, "MSI file should fail validation"
        assert any("Invalid MIME type" in reason for reason in reasons), (
            f"Expected 'Invalid MIME type' reason, got: {reasons}"
        )

    def test_disallowed_com_file(self, tmp_path: Path, monkeypatch) -> None:
        """Test that COM files fail validation."""
        com_file = tmp_path / "test.com"
        com_file.write_text("dummy content")

        monkeypatch.setattr(
            "spectrumx.ops.files.get_file_media_type",
            lambda _path: "application/x-msdos-program",
        )

        is_valid, reasons = is_valid_file(com_file)
        assert is_valid is False, "COM file should fail validation"
        assert any("Invalid MIME type" in reason for reason in reasons), (
            f"Expected 'Invalid MIME type' reason, got: {reasons}"
        )

    def test_disallowed_glob_patterns(self, tmp_path: Path) -> None:
        """Test that files matching disallowed glob patterns fail validation."""
        # Load actual disallowed patterns from .sds-ignore file
        disallowed_globs = _load_undesired_globs()
        # Create test files that match some of the disallowed patterns
        # We'll test patterns that are known to be in the .sds-ignore file
        test_cases = [
            ("test.tmp", "*.tmp"),
            ("index.html.tmp", "*.tmp.*"),
            ("backup.log", "*.log"),
            ("app.log", "*.log"),
            ("test.tmp.backup", "*.tmp.*"),
            ("config.env", "*.env"),
            ("myfile.secret", "*.*secret"),
        ]

        for filename, expected_pattern in test_cases:
            test_file = tmp_path / filename
            test_file.write_text("test content")

            # Verify that this filename matches the expected pattern
            matches_pattern = any(test_file.match(glob) for glob in disallowed_globs)
            assert matches_pattern, (
                f"File {filename} should match pattern {expected_pattern} "
                f"from .sds-ignore. Available patterns: {disallowed_globs}"
            )

            # Test that the file fails validation due to the glob pattern
            is_valid, reasons = is_valid_file(test_file)
            assert is_valid is False, (
                f"File {filename} should fail validation due to glob pattern "
                f"{expected_pattern}"
            )
            assert any("undesired glob patterns" in reason for reason in reasons), (
                f"No glob pattern reason found for {filename}"
            )

    def test_multiple_validation_failures(self, tmp_path: Path) -> None:
        """Test that multiple validation failures are all reported."""
        # Create a file that fails multiple checks
        bad_file = tmp_path / "test.exe.tmp"  # Both disallowed MIME and glob
        bad_file.touch()  # Empty file

        is_valid, reasons = is_valid_file(bad_file)
        assert is_valid is False, "File with multiple issues should fail validation"

        # Should have multiple reasons
        min_reasons = 2
        assert len(reasons) >= min_reasons, f"Expected multiple reasons, got: {reasons}"

        # Check for specific reasons
        reason_text = " ".join(reasons)
        assert "Empty file" in reason_text or "Invalid MIME type" in reason_text, (
            f"Expected 'Empty file' or 'Invalid MIME type' in reasons, got: {reasons}"
        )
        assert "undesired glob patterns" in reason_text, (
            f"Expected 'undesired glob patterns' in reasons, got: {reasons}"
        )

    def test_check_sds_ignore_disabled(self, tmp_path: Path) -> None:
        """Test that disabling SDS ignore check allows glob-patterned files."""
        tmp_file = tmp_path / "test.tmp"
        tmp_file.write_text("test content")

        # With SDS ignore check disabled, should pass
        is_valid, reasons = is_valid_file(tmp_file, check_sds_ignore=False)
        assert is_valid is True, (
            f"File should pass when SDS ignore is disabled. Reasons: {reasons}"
        )
        assert reasons == [], "No reasons should be given when SDS ignore is disabled"

    def test_large_valid_file(self, tmp_path: Path) -> None:
        """Test that a large valid file passes validation."""
        large_file = tmp_path / "large.txt"
        # Create a 1MB file
        content = "A" * 1024 * 1024
        large_file.write_text(content)

        is_valid, reasons = is_valid_file(large_file)
        assert is_valid is True, (
            f"Large valid file should pass validation. Reasons: {reasons}"
        )
        assert reasons == [], "No reasons should be given for valid files"


# =============================================================================
# sds_files.py coverage tests (phase 2)
# =============================================================================


def test_upload_file_invalid_type(client: Client) -> None:
    """upload_file raises TypeError for non-File/Path/str input."""
    with pytest.raises(TypeError, match="file_path must be a Path, str, or File"):
        client.upload_file(local_file=123)  # type: ignore[arg-type]


def test_upload_file_instance_directory_composition(
    client: Client, tmp_path: Path
) -> None:
    """Uploading a File instance with directory set prepends sds_path."""
    client.dry_run = True
    sub_path = PurePosixPath("sub/dir")
    file_path = tmp_path / "test_compose.txt"
    file_path.write_text("content")

    file_instance = File(
        uuid=uuidlib.uuid4(),
        name=file_path.name,
        media_type="text/plain",
        size=file_path.stat().st_size,
        directory=sub_path,
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
        local_path=file_path,
    )

    result = client.upload_file(
        local_file=file_instance,
        sds_path=PurePosixPath("/base"),
    )

    assert result.directory == PurePosixPath("/base/sub/dir"), (
        f"Expected '/base/sub/dir', got '{result.directory}'"
    )


def test_upload_file_skip_mode(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """When file already exists in tree, upload_file returns input without UUID."""
    client.dry_run = False
    asset_id = uuidlib.uuid4()

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": True,
            "user_mutable_attributes_differ": False,
            "asset_id": asset_id.hex,
        },
    )

    result = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/skip"),
    )

    assert result.uuid is None, "SKIP mode should return the local file without UUID"
    assert result.local_path == temp_file_with_text_contents
    assert len(responses.calls) == 1, "Only content-check request expected"


def test_upload_file_metadata_only_mode(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """When contents exist for user, upload metadata only."""
    client.dry_run = False
    asset_id = uuidlib.uuid4()
    file_id = uuidlib.uuid4()
    file_size = temp_file_with_text_contents.stat().st_size

    # content-check response: contents exist for user but not in tree
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": True,
            "asset_id": asset_id.hex,
        },
    )

    # metadata-only upload response
    responses.add(
        method=responses.POST,
        url=get_files_endpoint(client),
        status=201,
        json={
            "uuid": file_id.hex,
            "name": temp_file_with_text_contents.name,
            "media_type": "text/plain",
            "size": file_size,
            "directory": "/test/metadata-only",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    result = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/metadata-only"),
    )

    assert result.uuid == file_id, "Metadata-only upload should return a server File"
    assert result.directory == PurePosixPath("/test/metadata-only")
    assert len(responses.calls) == 2, "Expected content-check + metadata-upload calls"


def test_download_file_with_file_instance(
    client: Client, responses: responses.RequestsMock
) -> None:
    """download_file accepts a File instance directly."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    file_contents = "downloaded via file-instance"

    now_ts = datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC)

    file_instance = File(
        uuid=file_id,
        name="test.txt",
        media_type="text/plain",
        size=len(file_contents),
        directory=PurePosixPath("/test/"),
        permissions="rw-r--r--",
        created_at=now_ts,
        updated_at=now_ts,
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    # only the download endpoint is needed (file info is in the instance)
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=200,
        body=file_contents,
    )

    result = download_file(client=client, file_instance=file_instance)

    assert result.uuid == file_id
    assert result.local_path is not None
    assert result.local_path.exists()
    assert result.local_path.read_text() == file_contents

    # cleanup
    result.local_path.unlink(missing_ok=True)


def test_download_file_skip_contents(
    client: Client, responses: responses.RequestsMock
) -> None:
    """skip_contents=True prevents downloading file contents."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    now_ts = datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC)

    file_instance = File(
        uuid=file_id,
        name="test.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/test/"),
        permissions="rw-r--r--",
        created_at=now_ts,
        updated_at=now_ts,
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    # Do NOT register a download endpoint — if skip_contents works,
    # the download endpoint should NOT be called.
    result = download_file(
        client=client,
        file_instance=file_instance,
        skip_contents=True,
    )

    assert result.uuid == file_id
    assert result.local_path is None, "No local path should be set when skipping"
    assert len(responses.calls) == 0, "No HTTP calls should be made"


def test_download_file_missing_uuid(client: Client) -> None:
    """Downloading a File instance without a UUID raises ValueError."""
    now_ts = datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC)

    file_instance = File(
        name="test.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/test/"),
        permissions="rw-r--r--",
        created_at=now_ts,
        updated_at=now_ts,
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    with pytest.raises(ValueError, match="local reference"):
        download_file(client=client, file_instance=file_instance)


def test_download_file_contents_error_cleanup(
    client: Client, tmp_path: Path, responses: responses.RequestsMock
) -> None:
    """When download fails, temp files are cleaned up and exception propagates."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    target_path = tmp_path / "should-not-exist.txt"
    now_ts = datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC)

    file_instance = File(
        uuid=file_id,
        name="test.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/test/"),
        permissions="rw-r--r--",
        created_at=now_ts,
        updated_at=now_ts,
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=500,
        json={"detail": "Simulated download failure"},
    )

    with pytest.raises(SDSError, match="Simulated download failure"):
        download_file(
            client=client,
            file_instance=file_instance,
            to_local_path=target_path,
        )

    assert not target_path.exists(), (
        "Target path should not exist after failed download"
    )
    # verify no stray .downloading temp files remain
    temp_files = list(tmp_path.glob("*.downloading"))
    assert len(temp_files) == 0, f"Temp files not cleaned up: {temp_files}"


def test_delete_file_get_file_fails(
    client: Client, responses: responses.RequestsMock
) -> None:
    """When get_file fails before deletion, a warning is logged but delete proceeds."""
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False

    # GET request for file info will receive a response that causes parse failure
    responses.add(
        method=responses.GET,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        body=b"not-valid-json",
    )

    # DELETE request succeeds
    responses.add(
        method=responses.DELETE,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )

    result = delete_file(client=client, file_uuid=test_uuid)

    assert result is True, "Delete should succeed even if get_file fails"
    assert len(responses.calls) == 2, "Expected GET + DELETE calls"


def test_delete_file_cleanup_called(
    client: Client, responses: responses.RequestsMock
) -> None:
    """When sum_blake3 is set and delete succeeds, cleanup is triggered."""
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    test_checksum = "abc123def456"
    client.dry_run = False

    # GET returns file info WITH sum_blake3
    responses.add(
        method=responses.GET,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        json={
            "uuid": test_uuid_hex,
            "name": "test.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/test/",
            "permissions": "rw-r--r--",
            "sum_blake3": test_checksum,
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    # DELETE request succeeds
    responses.add(
        method=responses.DELETE,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )

    with patch.object(
        UploadPersistenceManager,
        "remove_persisted_uploads_by_checksum",
    ) as mock_cleanup:
        result = delete_file(client=client, file_uuid=test_uuid)

        assert result is True
        mock_cleanup.assert_called_once_with(checksum=test_checksum)

    assert len(responses.calls) == 2, "Expected GET + DELETE calls"


def test_delete_file_gateway_returns_false(
    client: Client, responses: responses.RequestsMock
) -> None:
    """When the gateway rejects the DELETE, the error propagates as FileError."""
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False

    # GET returns file info
    responses.add(
        method=responses.GET,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        json={
            "uuid": test_uuid_hex,
            "name": "test.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/test/",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    responses.add(
        method=responses.DELETE,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=400,
        json={"detail": "Cannot delete"},
    )

    with pytest.raises(FileError, match="Cannot delete"):
        delete_file(client=client, file_uuid=test_uuid)


def test_list_files_empty_result(
    client: Client, responses: responses.RequestsMock
) -> None:
    """list_files returns no files when the gateway returns an empty page."""
    client.dry_run = False

    responses.add(
        method=responses.GET,
        url=get_files_endpoint(client),
        status=200,
        json={"count": 0, "results": []},
    )

    paginator = list_files(
        client=client,
        sds_path=PurePosixPath("/test/empty"),
    )
    results = list(paginator)

    assert results == [], "Expected no files from empty listing"


def test_list_files_dry_run(client: Client) -> None:
    """list_files in dry run returns a paginator without network calls."""
    client.dry_run = True

    paginator = list_files(
        client=client,
        sds_path=PurePosixPath("/test/dry"),
    )

    # In dry run, the paginator yields sample files
    results = list(paginator)
    assert len(results) > 0, "Expected sample files in dry run"
    for f in results:
        assert f.uuid is not None
        assert isinstance(f.name, str)
        assert len(f.name) > 0


def test_cleanup_persisted_uploads_error(
    client: Client, responses: responses.RequestsMock
) -> None:
    """When UploadPersistenceManager raises, the error is logged but not re-raised."""
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False

    # GET returns file info WITH sum_blake3
    responses.add(
        method=responses.GET,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=200,
        json={
            "uuid": test_uuid_hex,
            "name": "test.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/test/",
            "permissions": "rw-r--r--",
            "sum_blake3": "somechecksum",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    # DELETE succeeds
    responses.add(
        method=responses.DELETE,
        url=f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )

    with patch.object(
        UploadPersistenceManager,
        "remove_persisted_uploads_by_checksum",
        side_effect=OSError("Disk error"),
    ):
        # Should NOT raise — error is caught and logged
        result = delete_file(client=client, file_uuid=test_uuid)

    assert result is True, "Delete should still succeed even if cleanup fails"
    assert len(responses.calls) == 2, "Expected GET + DELETE calls"


# =============================================================================
# Phase 3 coverage: download_file variants
# =============================================================================


def test_download_file_empty_204_response(
    client: Client, responses: responses.RequestsMock
) -> None:
    """204 No Content download creates an empty local file."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    num_bytes = 0

    responses.add(
        method=responses.GET,
        url=_get_file_id_endpoint(client, file_id=file_id.hex),
        status=200,
        json={
            "uuid": file_id.hex,
            "name": "empty.txt",
            "media_type": "text/plain",
            "size": num_bytes,
            "directory": "/empty/",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=204,
    )

    result = download_file(client=client, file_uuid=file_id.hex)
    downloaded_path = result.local_path
    assert downloaded_path is not None, "Returned path must not be None"
    assert downloaded_path.exists(), "File was not created"
    assert downloaded_path.stat().st_size == num_bytes, (
        f"Expected empty file, got {downloaded_path.stat().st_size} bytes"
    )

    downloaded_path.unlink(missing_ok=True)


def test_download_file_to_directory_path(
    client: Client, responses: responses.RequestsMock, tmp_path: Path
) -> None:
    """to_local_path pointing to a directory uses that exact path as the file."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    file_contents = "content for dir-test"
    num_bytes = len(file_contents.encode("utf-8"))
    target_dir = tmp_path / "subdir"
    expected_path = target_dir  # path passed as if it were a file

    responses.add(
        method=responses.GET,
        url=_get_file_id_endpoint(client, file_id=file_id.hex),
        status=200,
        body=json.dumps(
            {
                "uuid": file_id.hex,
                "name": "test.txt",
                "media_type": "text/plain",
                "size": num_bytes,
                "directory": "/test/",
                "permissions": "rw-r--r--",
                "created_at": "2024-12-01T12:00:00Z",
                "updated_at": "2024-12-01T12:00:00Z",
                "expiration_date": "2026-12-01T12:00:00Z",
            }
        ),
    )
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=200,
        body=file_contents,
    )

    result = download_file(
        client=client, file_uuid=file_id.hex, to_local_path=target_dir
    )
    downloaded_path = result.local_path
    assert downloaded_path == expected_path
    assert downloaded_path is not None
    assert downloaded_path.exists()
    assert downloaded_path.stat().st_size == num_bytes

    downloaded_path.unlink(missing_ok=True)


def test_download_file_with_progress_callback(
    client: Client, responses: responses.RequestsMock
) -> None:
    """download_file invokes progress_callback with chunk byte counts."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    file_contents = "x" * 20000
    num_bytes = len(file_contents.encode("utf-8"))

    responses.add(
        method=responses.GET,
        url=_get_file_id_endpoint(client, file_id=file_id.hex),
        status=200,
        body=json.dumps(
            {
                "uuid": file_id.hex,
                "name": "progress_test.txt",
                "media_type": "text/plain",
                "size": num_bytes,
                "directory": "/progress/",
                "permissions": "rw-r--r--",
                "created_at": "2024-12-01T12:00:00Z",
                "updated_at": "2024-12-01T12:00:00Z",
                "expiration_date": "2026-12-01T12:00:00Z",
            }
        ),
    )
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=200,
        body=file_contents,
    )

    chunks_received: list[int] = []

    def _callback(byte_count: int) -> None:
        chunks_received.append(byte_count)

    result = download_file(
        client=client,
        file_uuid=file_id.hex,
        progress_callback=_callback,
    )
    assert result.local_path is not None
    assert result.local_path.exists()
    assert len(chunks_received) > 0, "progress_callback was never called"
    assert sum(chunks_received) == num_bytes, (
        f"Expected {num_bytes} bytes total, got {sum(chunks_received)}"
    )

    result.local_path.unlink(missing_ok=True)


# =============================================================================
# Phase 3 coverage: delete_file edge cases
# =============================================================================


def test_delete_file_via_patch_gateway_returns_false(
    client: Client,
) -> None:
    """When gateway.delete_file_by_id returns False, delete_file returns False."""
    test_uuid = uuidlib.uuid4()
    client.dry_run = False

    with (
        patch.object(client._gateway, "delete_file_by_id", return_value=False),
        patch.object(
            client._gateway,
            "get_file_by_id",
            return_value=b'{"uuid":"' + test_uuid.hex.encode() + b'","name":"test.txt",'
            b'"media_type":"text/plain","size":100,"directory":"/test/",'
            b'"permissions":"rw-r--r--","sum_blake3":"somechecksum",'
            b'"created_at":"2024-12-01T12:00:00Z",'
            b'"updated_at":"2024-12-01T12:00:00Z",'
            b'"expiration_date":"2026-12-01T12:00:00Z"}',
        ),
    ):
        result = delete_file(client=client, file_uuid=test_uuid)

    assert result is False, "Expected delete_file to return False"


# =============================================================================
# Phase 3 coverage: list_files pagination & temporal edge cases
# =============================================================================


def test_list_files_multiple_pages(
    client: Client, responses: responses.RequestsMock
) -> None:
    """list_files paginates across multiple result pages."""
    client.dry_run = False
    page_size = 2
    total_count = 3

    page1_results = [
        {
            "uuid": uuidlib.uuid4().hex,
            "name": f"file_{i}.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/multi/",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        }
        for i in range(page_size)
    ]
    page2_results = [
        {
            "uuid": uuidlib.uuid4().hex,
            "name": "file_2.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/multi/",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        }
    ]

    responses.add(
        method=responses.GET,
        url=get_files_endpoint(client),
        status=200,
        json={"count": total_count, "results": page1_results},
    )
    responses.add(
        method=responses.GET,
        url=get_files_endpoint(client),
        status=200,
        json={"count": total_count, "results": page2_results},
    )

    paginator = list_files(
        client=client,
        sds_path=PurePosixPath("/multi"),
    )
    # Replace page_size to ensure multiple fetches with our data
    paginator._page_size = page_size  # pyright: ignore[reportPrivateUsage]
    results = list(paginator)

    assert len(results) == total_count, (
        f"Expected {total_count} files, got {len(results)}"
    )
    assert len(responses.calls) == 2, "Expected 2 page requests"


def test_list_files_temporal_inverted_range(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Inverted temporal range (start > end) returns empty results gracefully."""
    client.dry_run = False
    start = datetime(2024, 6, 28, 14, 0, 0, tzinfo=UTC)
    end = datetime(2024, 6, 27, 14, 0, 0, tzinfo=UTC)
    expected_start_q = file_list_time_query_param(start)
    expected_end_q = file_list_time_query_param(end)

    empty_page = b'{"count": 0, "results": []}'

    with patch.object(client._gateway, "list_files", return_value=empty_page) as m_list:
        paginator = list_files(
            client=client,
            sds_path=PurePosixPath("/temporal"),
            start_time=start,
            end_time=end,
        )
        results = list(paginator)

    assert results == [], "Expected empty result for inverted range"
    for call in m_list.call_args_list:
        kw = call.kwargs
        assert kw["start_time"] == expected_start_q
        assert kw["end_time"] == expected_end_q


def test_list_files_temporal_zero_width_range(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Zero-width temporal range (start == end) is valid and sent as-is."""
    client.dry_run = False
    t = datetime(2024, 6, 27, 14, 0, 0, tzinfo=UTC)
    expected_q = file_list_time_query_param(t)

    empty_page = b'{"count": 0, "results": []}'

    with patch.object(client._gateway, "list_files", return_value=empty_page) as m_list:
        paginator = list_files(
            client=client,
            sds_path=PurePosixPath("/temporal"),
            start_time=t,
            end_time=t,
        )
        list(paginator)

    m_list.assert_called()
    for call in m_list.call_args_list:
        kw = call.kwargs
        assert kw["start_time"] == expected_q
        assert kw["end_time"] == expected_q


# =============================================================================
# Phase 3 coverage: upload_file SKIP mode with differ flag
# =============================================================================


def test_upload_file_skip_mode_with_differ(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """SKIP mode returns local file when file_exists_in_tree even with differ=True."""
    client.dry_run = False
    asset_id = uuidlib.uuid4()

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": True,
            "user_mutable_attributes_differ": True,
            "asset_id": asset_id.hex,
        },
    )

    result = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/differ"),
    )

    assert result.uuid is None, "SKIP mode should return the local file without UUID"
    assert result.local_path == temp_file_with_text_contents
    assert len(responses.calls) == 1, "Only content-check request expected"


# =============================================================================
# Phase 3 coverage: upload_file progress_callback in metadata-only path
# =============================================================================


def test_upload_file_metadata_only_with_progress_callback(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """Metadata-only upload accepts (and ignores) progress_callback."""
    client.dry_run = False
    asset_id = uuidlib.uuid4()
    file_id = uuidlib.uuid4()
    file_size = temp_file_with_text_contents.stat().st_size

    # content-check: contents exist for user, not in tree → UPLOAD_METADATA_ONLY
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": True,
            "asset_id": asset_id.hex,
        },
    )

    responses.add(
        method=responses.POST,
        url=get_files_endpoint(client),
        status=201,
        json={
            "uuid": file_id.hex,
            "name": temp_file_with_text_contents.name,
            "media_type": "text/plain",
            "size": file_size,
            "directory": "/test/meta-progress",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    callback_invoked = False

    def _callback(_bytes: int) -> None:
        nonlocal callback_invoked
        callback_invoked = True

    result = upload_file(
        client=client,
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/meta-progress"),
        progress_callback=_callback,
    )

    assert result.uuid == file_id
    assert result.directory == PurePosixPath("/test/meta-progress")
    # progress_callback is not used in metadata-only path (no contents to upload)
    assert callback_invoked is False


# =============================================================================
# Phase 3 coverage: remaining uncovered lines in sds_files.py
# =============================================================================


def test_upload_file_instance_without_directory(client: Client, tmp_path: Path) -> None:
    """Uploading a File with no directory set does not compose sds_path."""
    client.dry_run = True
    file_path = tmp_path / "test_no_dir.txt"
    file_path.write_text("content")

    # directory defaults to PurePosixPath() (empty / falsy)
    file_instance = File(
        name=file_path.name,
        media_type="text/plain",
        size=file_path.stat().st_size,
        directory=PurePosixPath(),
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
        local_path=file_path,
    )

    result = client.upload_file(
        local_file=file_instance,
        sds_path=PurePosixPath("/base"),
    )

    # directory stays as default (empty PurePosixPath) since it was falsy
    assert result.directory == PurePosixPath("/base"), (
        f"Expected '/base', got '{result.directory}' — "
        "directory should not be composed when empty"
    )


def test_download_file_dry_run(
    client: Client,
) -> None:
    """download_file in dry_run returns sample without network calls."""
    client.dry_run = True
    file_id = uuidlib.uuid4()

    result = download_file(client=client, file_uuid=file_id.hex)

    assert result.uuid == file_id
    assert result.local_path is None, (
        "No local path should be set in dry_run without to_local_path"
    )


def test_download_file_no_identifier(
    client: Client,
) -> None:
    """download_file without file_instance or file_uuid raises ValueError."""
    with pytest.raises(ValueError, match="Expected a file instance or UUID"):
        download_file(client=client)


def test_upload_file_skip_verbose(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """SKIP mode with verbose logs a message."""
    client.dry_run = False
    client.verbose = True
    asset_id = uuidlib.uuid4()

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": True,
            "user_mutable_attributes_differ": False,
            "asset_id": asset_id.hex,
        },
    )

    result = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/skip-verbose"),
    )

    assert result.uuid is None, "SKIP mode should return local file"


def test_upload_file_contents_verbose(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """Upload-contents mode with verbose logs a message."""
    client.dry_run = False
    client.verbose = True
    file_id = uuidlib.uuid4()
    file_size = temp_file_with_text_contents.stat().st_size

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": False,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": True,
        },
    )
    responses.add(
        method=responses.POST,
        url=get_files_endpoint(client),
        status=201,
        json={
            "uuid": file_id.hex,
            "name": temp_file_with_text_contents.name,
            "media_type": "text/plain",
            "size": file_size,
            "directory": "/test/contents-verbose",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    result = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/contents-verbose"),
    )

    assert result.uuid == file_id


def test_upload_file_metadata_only_missing_asset_id(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """Metadata-only upload raises SDSError when asset_id is None."""
    client.dry_run = False

    # content-check: contents exist but asset_id is None
    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": True,
            "asset_id": None,
        },
    )

    with pytest.raises(SDSError, match="Expected an asset ID"):
        upload_file(
            client=client,
            local_file=temp_file_with_text_contents,
            sds_path=PurePosixPath("/test/no-asset"),
        )


def test_upload_contents_and_metadata_dry_run(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """Dry-run in __upload_contents_and_metadata logs and returns early."""
    client.dry_run = True

    result = client.upload_file(
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/dry-contents"),
    )

    assert result.local_path == temp_file_with_text_contents
    assert result.uuid is None


def test_upload_new_file_metadata_only_dry_run(
    client: Client,
) -> None:
    """Dry-run in __upload_new_file_metadata_only logs and returns early."""
    file_instance = File(
        name="dry_meta.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/dry/meta"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    result = __upload_new_file_metadata_only(
        client=client,
        file_instance=file_instance,
        sibling_uuid=uuidlib.uuid4(),
    )

    assert result is file_instance, "Should return the input file instance unchanged"


def test_update_existing_file_metadata_only_updates_metadata(
    client: Client,
) -> None:
    """asset_id=None leaves uuid unchanged (no update sent)."""
    client.dry_run = True
    file_instance = File(
        name="update_meta.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/update/meta"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )
    result = __update_existing_file_metadata_only(
        client=client,
        file_instance=file_instance.model_copy(),
        asset_id=None,
    )
    assert result.uuid is None, "uuid should remain None when asset_id is None"


def test_update_existing_file_metadata_only_preserves_file(
    client: Client,
) -> None:
    """dry_run returns early with asset_id set on file_instance (no PUT)."""
    client.dry_run = True
    asset_id = uuidlib.uuid4()
    file_instance = File(
        name="update_meta.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/update/meta"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )
    result = __update_existing_file_metadata_only(
        client=client,
        file_instance=file_instance.model_copy(),
        asset_id=asset_id,
    )
    assert result.uuid == asset_id, (
        "asset_id should be set on file_instance even in dry_run"
    )


def test_update_existing_file_metadata_only_no_download(
    client: Client,
    responses: responses.RequestsMock,
) -> None:
    """non-dry_run sends PUT and returns updated File with server UUID."""
    client.dry_run = False
    asset_id = uuidlib.uuid4()
    updated_uuid = uuidlib.uuid4()
    file_instance = File(
        name="update_meta.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/update/meta"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )
    file_instance.uuid = asset_id

    responses.add(
        method=responses.PUT,
        url=f"{get_files_endpoint(client)}{asset_id.hex}/",
        status=200,
        json={
            "uuid": updated_uuid.hex,
            "name": "update_meta.txt",
            "media_type": "text/plain",
            "size": 100,
            "directory": "/update/meta",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    result = __update_existing_file_metadata_only(
        client=client,
        file_instance=file_instance,
        asset_id=asset_id,
    )
    assert result.uuid == updated_uuid


def test_download_file_contents_dry_run(
    client: Client,
) -> None:
    """__download_file_contents dry-run logs and returns the target path."""
    file_id = uuidlib.uuid4()
    client.dry_run = True
    contents_lock = RLock()

    result = __download_file_contents(
        client=client,
        file_uuid=file_id,
        contents_lock=contents_lock,
        target_path=None,
    )

    assert result is not None
    assert isinstance(result, Path)


def test_upload_file_metadata_only_verbose(
    client: Client,
    responses: responses.RequestsMock,
    temp_file_with_text_contents: Path,
) -> None:
    """Metadata-only upload with verbose logs additional messages."""
    client.dry_run = False
    client.verbose = True
    asset_id = uuidlib.uuid4()
    file_id = uuidlib.uuid4()
    file_size = temp_file_with_text_contents.stat().st_size

    responses.add(
        method=responses.POST,
        url=get_content_check_endpoint(client),
        status=201,
        json={
            "file_contents_exist_for_user": True,
            "file_exists_in_tree": False,
            "user_mutable_attributes_differ": True,
            "asset_id": asset_id.hex,
        },
    )

    responses.add(
        method=responses.POST,
        url=get_files_endpoint(client),
        status=201,
        json={
            "uuid": file_id.hex,
            "name": temp_file_with_text_contents.name,
            "media_type": "text/plain",
            "size": file_size,
            "directory": "/test/meta-verbose",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )

    result = upload_file(
        client=client,
        local_file=temp_file_with_text_contents,
        sds_path=PurePosixPath("/test/meta-verbose"),
    )

    assert result.uuid == file_id


def test_upload_contents_and_metadata_dry_run_direct(
    client: Client,
) -> None:
    """__upload_contents_and_metadata dry-run logs and returns the input."""
    client.dry_run = True
    file_id = uuidlib.uuid4()
    file_instance = File(
        uuid=file_id,
        name="dry_content.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/dry/content"),
        permissions="rw-r--r--",
        created_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        updated_at=datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC),
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    result = __upload_contents_and_metadata(
        client=client,
        file_instance=file_instance,
    )

    assert result is file_instance, "Should return the input file instance unchanged"


def test_download_file_temp_target_failure(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Download failure with temp target does not attempt cleanup (branch 394->396)."""
    client.dry_run = False
    file_id = uuidlib.uuid4()
    now_ts = datetime(2024, 12, 1, 12, 0, 0, tzinfo=UTC)

    file_instance = File(
        uuid=file_id,
        name="temp_fail.txt",
        media_type="text/plain",
        size=100,
        directory=PurePosixPath("/test/"),
        permissions="rw-r--r--",
        created_at=now_ts,
        updated_at=now_ts,
        expiration_date=datetime(2026, 12, 1, 12, 0, 0, tzinfo=UTC),
    )

    # No file metadata endpoint needed — File instance has the info
    # Mock download to fail
    responses.add(
        method=responses.GET,
        url=_download_file_endpoint(client, file_id=file_id.hex),
        status=500,
        json={"detail": "Simulated failure"},
    )

    with pytest.raises(SDSError):
        download_file(
            client=client,
            file_instance=file_instance,
            # to_local_path deliberately omitted → is_temp_target=True
        )
