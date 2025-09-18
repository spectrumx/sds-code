"""Tests file operations."""
# pylint: disable=redefined-outer-name

import json
import sys
import tempfile
import uuid as uuidlib
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath

import pytest
import responses
from loguru import logger as log
from spectrumx import Client
from spectrumx.api.sds_files import delete_file
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.ops.files import _load_undesired_globs
from spectrumx.ops.files import get_file_permissions
from spectrumx.ops.files import is_valid_file

from tests.conftest import get_content_check_endpoint
from tests.conftest import get_files_endpoint

log.trace("Placeholder log to avoid reimporting or resolving unused import warnings.")


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
        assert get_file_permissions(temp_file_empty) == perm_string


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
        assert get_file_permissions(temp_file_empty) == perm_string


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
    assert file_sample.directory == PurePosixPath("sds-files/dry-run/")
    assert file_sample.permissions == "rw-rw-r--"
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
    assert isinstance(file_sample.expiration_date, datetime), (
        "Expiration date should be a datetime"
    )
    assert file_sample.expiration_date > file_sample.created_at


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
    assert file_sample.directory == PurePosixPath("/my/upload/location")
    expected_permissions = "rw-rw-rw-" if sys.platform == "win32" else "rw-r--r--"
    assert file_sample.permissions == expected_permissions

    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)
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
    assert file_sample.name == mocked_upload_json["name"]
    assert file_sample.media_type == mocked_upload_json["media_type"]
    assert file_sample.size == file_size
    assert file_sample.directory == PurePosixPath(mocked_upload_json["directory"])
    assert file_sample.permissions == mocked_upload_json["permissions"]
    assert isinstance(file_sample.created_at, datetime)
    assert isinstance(file_sample.updated_at, datetime)


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


@responses.activate
def test_delete_file_success(client: Client) -> None:
    """Test successful file deletion."""
    # ARRANGE
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False
    assert client.dry_run is False, "Dry run must be enabled for this test."
    responses.add(
        responses.DELETE,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )

    # ACT
    result = delete_file(client=client, file_uuid=test_uuid)

    # ASSERT
    assert result is True, "Expected deletion to succeed."
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "DELETE"
    assert (
        responses.calls[0].request.url
        == f"{get_files_endpoint(client)}{test_uuid_hex}/"
    )


@responses.activate
def test_delete_file_str_uuid(client: Client) -> None:
    """Test file deletion with string UUID."""
    # ARRANGE
    test_uuid = uuidlib.uuid4()
    test_uuid_hex = test_uuid.hex
    client.dry_run = False  # calls are mocked, but we want to test the actual requests
    assert client.dry_run is False, "Dry run must be enabled for this test."
    responses.add(
        responses.DELETE,
        f"{get_files_endpoint(client)}{test_uuid_hex}/",
        status=204,
    )

    # ACT
    result = delete_file(client=client, file_uuid=test_uuid_hex)

    # ASSERT
    assert result is True, "Expected deletion to succeed."
    assert len(responses.calls) == 1, "Expected one DELETE request to be made."
    assert responses.calls[0].request.method == "DELETE"
    assert (
        responses.calls[0].request.url
        == f"{get_files_endpoint(client)}{test_uuid_hex}/"
    )


@responses.activate
def test_delete_file_dry_run(client: Client) -> None:
    """Test file deletion in dry run mode."""
    # ARRANGE
    test_uuid = uuidlib.uuid4()
    assert client.dry_run is True, "Dry run must be enabled for this test."

    # ACT
    result = delete_file(client=client, file_uuid=test_uuid)

    # ASSERT
    assert result is True  # deletion always succeeds in dry run mode
    assert len(responses.calls) == 0


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
        assert "Empty file, or could not read it" in reasons

    def test_nonexistent_file(self, tmp_path: Path) -> None:
        """Test that a nonexistent file fails validation."""
        nonexistent_file = tmp_path / "nonexistent.txt"

        is_valid, reasons = is_valid_file(nonexistent_file)
        assert is_valid is False, "Nonexistent file should fail validation"
        assert "Not a file" in reasons

    def test_directory_instead_of_file(self, tmp_path: Path) -> None:
        """Test that a directory fails validation."""
        test_dir = tmp_path / "test_dir"
        test_dir.mkdir()

        is_valid, reasons = is_valid_file(test_dir)
        assert is_valid is False, "Directory should fail validation"
        assert "Not a file" in reasons

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
        assert any("Invalid MIME type" in reason for reason in reasons)

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
        assert any("Invalid MIME type" in reason for reason in reasons)

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
        assert any("Invalid MIME type" in reason for reason in reasons)

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
        assert "Empty file" in reason_text or "Invalid MIME type" in reason_text
        assert "undesired glob patterns" in reason_text

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
