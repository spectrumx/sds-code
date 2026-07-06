"""Tests for the client module."""

# pyright: reportPrivateUsage=false

import re
import uuid
from enum import IntEnum
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import UUID

import pytest
import responses
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.client import _normalize_top_level_dir_prefix
from spectrumx.client import resolve_dataset_capture_filter_params
from spectrumx.config import CFG_NAME_LOOKUP
from spectrumx.config import SDSConfig
from spectrumx.errors import CaptureError
from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.models.captures import CaptureType
from spectrumx.models.files import File
from spectrumx.ops import files

from tests.conftest import get_captures_endpoint
from tests.conftest import get_content_check_endpoint
from tests.conftest import get_datasets_endpoint
from tests.conftest import get_files_endpoint

_DRY_RUN_FILE_COUNT = 10


class LogLevels(IntEnum):
    """Log levels for testing."""

    TRACE = 5
    DEBUG = 10
    INFO = 20
    WARNING = 30
    ERROR = 40
    CRITICAL = 50


def test_load_config_env_file_not_found(caplog: pytest.LogCaptureFixture) -> None:
    """When the env file is not found, a warning must be logged."""

    non_existent_file = Path("non_existent.env")
    caplog.set_level(LogLevels.WARNING)
    SDSConfig(env_file=non_existent_file)

    assert "file missing" in caplog.text.lower(), (
        "Expected a warning about missing env file"
    )


def test_load_config_file_found(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    """A valid env file must be found and loaded."""

    filename = "existing.env"
    existing_file = tmp_path / filename
    existing_file.touch()
    caplog.set_level(LogLevels.DEBUG)
    SDSConfig(env_file=existing_file, verbose=True)

    pattern = f"found.*{filename}".lower()
    assert re.search(pattern, caplog.text.lower()), (
        "Expected log to contain 'found' and the filename"
    )


def test_load_config_from_args(sample_config: dict[str, Any]) -> None:
    """Ensures loading config from arguments works."""

    config = SDSConfig(env_file=Path(".env.example"), env_config=sample_config)

    for key, value in sample_config.items():
        norm_key = (
            CFG_NAME_LOOKUP[key.lower()].attr_name
            if key.lower() in CFG_NAME_LOOKUP
            else key.lower()
        )
        expected_value = value
        actual_value = getattr(config, norm_key)
        assert expected_value == actual_value, (
            f"Expected {expected_value}, got {actual_value}"
        )


def test_show_config_does_not_expose_api_key(
    sample_config: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Makes sure the API key is not exposed by show_config()."""

    config = SDSConfig(env_file=Path(".env.example"), env_config=sample_config)
    config.show_config()

    # this all_outputs approach should work for both `make test` and `make test-verbose`
    captured = capsys.readouterr()
    all_outputs = (captured.out + captured.err + caplog.text).lower()

    assert "api_key" in all_outputs, "Expected 'api_key' to appear in config output"
    assert sample_config["SDS_SECRET_TOKEN"] not in all_outputs, (
        "Expected API key value to NOT appear in config output"
    )


def test_warning_for_unrecognized_config(
    sample_config: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """A warning must be logged for unrecognized configuration."""

    unknown_attr = "UNRECOGNIZED_CONFIG"
    sample_config[unknown_attr] = "value"
    caplog.set_level(LogLevels.WARNING)
    SDSConfig(env_file=Path(".env.example"), env_config=sample_config)

    assert "not recognized" in caplog.text.lower(), (
        "Expected warning about unrecognized config"
    )
    assert unknown_attr in caplog.text, (
        "Expected the unknown config attribute name in log"
    )


# ======================================================================
# Regression tests: HTTP_TIMEOUT loading
# ======================================================================

_TEST_ENV_BASE = "SDS_HOST = sds-test.example.com\nSDS_SECRET_TOKEN = test-key-123\n"
_EXPECTED_DEFAULT_TIMEOUT = 300
_ENV_FILE_TIMEOUT = 99
_ENV_CONFIG_TIMEOUT = "77"
_ENV_FILE_TIMEOUT_LOWER = 50
_ENV_CONFIG_OVERRIDE_TIMEOUT = "88"
_ENV_FILE_TIMEOUT_GATEWAY = 65


def test_http_timeout_default() -> None:
    """Default timeout must be 300 when set via Client with no env overrides."""
    client = Client(host="sds-test.example.com")
    assert client.gateway.timeout == _EXPECTED_DEFAULT_TIMEOUT, (
        f"Expected default gateway timeout {_EXPECTED_DEFAULT_TIMEOUT}, "
        f"got {client.gateway.timeout}"
    )


def test_http_timeout_from_env_file(tmp_path: Path) -> None:
    """HTTP_TIMEOUT from .env file must propagate to GatewayClient."""
    env_file = tmp_path / ".env.test_timeout"
    env_content = f"HTTP_TIMEOUT = {_ENV_FILE_TIMEOUT}\n{_TEST_ENV_BASE}"
    env_file.write_text(env_content)
    client = Client(host="sds-test.example.com", env_file=env_file)
    assert client.gateway.timeout == _ENV_FILE_TIMEOUT, (
        f"Expected gateway timeout {_ENV_FILE_TIMEOUT} from .env file, "
        f"got {client.gateway.timeout}"
    )


def test_http_timeout_from_env_config() -> None:
    """HTTP_TIMEOUT from env_config dict must propagate to GatewayClient."""
    client = Client(
        host="sds-test.example.com",
        env_config={
            "HTTP_TIMEOUT": _ENV_CONFIG_TIMEOUT,
            "SDS_HOST": "sds-test.example.com",
            "SDS_SECRET_TOKEN": "test-key-123",
        },
    )
    assert client.gateway.timeout == int(_ENV_CONFIG_TIMEOUT), (
        f"Expected gateway timeout {_ENV_CONFIG_TIMEOUT} from env_config, "
        f"got {client.gateway.timeout}"
    )


def test_http_timeout_env_config_overrides_env_file(tmp_path: Path) -> None:
    """env_config must take precedence over .env file for HTTP_TIMEOUT."""
    env_file = tmp_path / ".env.test_override"
    env_content = f"HTTP_TIMEOUT = {_ENV_FILE_TIMEOUT_LOWER}\n{_TEST_ENV_BASE}"
    env_file.write_text(env_content)
    client = Client(
        host="sds-test.example.com",
        env_file=env_file,
        env_config={"HTTP_TIMEOUT": _ENV_CONFIG_OVERRIDE_TIMEOUT},
    )
    assert client.gateway.timeout == int(_ENV_CONFIG_OVERRIDE_TIMEOUT), (
        f"Expected gateway timeout {_ENV_CONFIG_OVERRIDE_TIMEOUT} "
        f"(env_config overrides .env), got {client.gateway.timeout}"
    )


def test_http_timeout_passed_to_gateway(tmp_path: Path) -> None:
    """HTTP_TIMEOUT from env must propagate to GatewayClient via Client."""
    env_file = tmp_path / ".env.test_gateway"
    env_content = f"HTTP_TIMEOUT = {_ENV_FILE_TIMEOUT_GATEWAY}\n{_TEST_ENV_BASE}"
    env_file.write_text(env_content)
    client = Client(host="sds-test.example.com", env_file=env_file)
    assert client.gateway.timeout == _ENV_FILE_TIMEOUT_GATEWAY, (
        f"Expected gateway timeout {_ENV_FILE_TIMEOUT_GATEWAY}, "
        f"got {client.gateway.timeout}"
    )


def test_download_dry_run_happy_path(
    caplog: pytest.LogCaptureFixture,
    client: Client,
) -> None:
    """Covers the client's generic download() method for files."""

    caplog.set_level(LogLevels.INFO)
    client.dry_run = True
    sds_path = "sds/path"
    local_path = "local/path"
    expected_length = 10  # how many files dry run generates by default

    results = client.download(
        from_sds_path=sds_path,
        to_local_path=local_path,
        verbose=True,
    )
    successful = [result() for result in results if result]
    errors = [result.error_info for result in results if not result]
    assert len(errors) == 0, "No errors should be present in this run."
    dry_run_msg = "Dry-run enabled: no SDS requests will be made or files written."
    assert dry_run_msg in caplog.text, (
        f"Expected dry-run message in logs, got: {caplog.text}"
    )
    assert len(results) == expected_length, (
        f"Expected {expected_length} results, got {len(results)}"
    )
    assert len(successful) == expected_length, (
        f"Expected {expected_length} successful downloads, got {len(successful)}"
    )
    non_sample_files = [file_obj for file_obj in successful if not file_obj.is_sample]
    assert not non_sample_files, (
        f"All files should be sample files in dry-run. "
        f"Non-sample files: {len(non_sample_files)}"
    )


def test_download_fails_for_invalid_files(
    caplog: pytest.LogCaptureFixture,
    client: Client,
) -> None:
    """Ensures download() fails when an invalid local path is provided."""

    caplog.set_level(LogLevels.ERROR)
    sds_path = PurePosixPath("sds/custom/dir/")
    local_path = Path("local/path")

    target_num_files = 2
    original_list = files.generate_random_files(num_files=target_num_files)

    def _get_problematic_list_of_files(num_files: int = 10) -> list[File]:
        """Generates a list of fabricated files with issues for download."""
        # num_files is ignored here 😈
        altered_list = [
            ofile.model_copy() for ofile in original_list[:target_num_files]
        ]

        # set an invalid directory (not a child of local_path)
        altered_list[0].directory = local_path / "../../../" / "invalid"

        # can't download a file with missing uuid for now
        altered_list[1].uuid = None

        return altered_list

    # Patch the files.generate_random_files method to return the problematic list
    with patch.object(
        files,
        attribute="generate_random_files",
        side_effect=_get_problematic_list_of_files,
    ):
        results = client.download(from_sds_path=sds_path, to_local_path=local_path)
        assert len(results) == target_num_files, "Three files should be generated"

        successful_files = [result() for result in results if result]
        error_infos = [result.error_info for result in results if not result]
        log.error(
            f"File count: successful={len(successful_files)}, "
            f"errored={len(error_infos)}"
        )
        for success in successful_files:
            log.info(f"{success.name}: {success.uuid}")
        for error in error_infos:
            assert "file" in error, "Error info should contain a file object."
            file_obj: File = error["file"]
            log.error(f"{file_obj.name}: uuid={file_obj.uuid}")
        assert not any(successful_files), "No file should be successfully downloaded."


def test_existing_local_file_no_overwrite_skips_download(
    tmp_path: Path, client: Client
) -> None:
    """When a file exists locally and overwrite is False, it must not be re-created."""

    sds_dir = PurePosixPath("remote/dir")
    # create sample file metadata
    file_info = files.generate_sample_file(uuid.uuid4())
    file_info.directory = sds_dir
    file_info.name = "existing.txt"

    # create local file that should cause the client to skip re-download
    local_target = Path(f"{tmp_path}/{sds_dir}") / file_info.name
    local_target.parent.mkdir(parents=True, exist_ok=True)
    local_target.write_text("local contents")

    # patch download_file to fail the test if called
    with patch.object(
        Client,
        "download_file",
        side_effect=AssertionError("download_file should not be called"),
    ):
        result = client.download_single_file(
            file_info=file_info,
            to_local_path=tmp_path,
            skip_contents=False,
            overwrite=False,
        )

    assert result, "Result should not be None"
    assert result() is file_info, "Returned file should be the original file_info"


def test_existing_local_file_overwrite_redownloads_it(
    tmp_path: Path, client: Client
) -> None:
    """When overwriting and local file differs, the file must be re-downloaded,
    thus discarding the local version."""

    sds_dir = PurePosixPath("remote")
    file_info = files.generate_sample_file(uuid.uuid4())
    file_info.directory = sds_dir
    file_info.name = "recreate.bin"

    local_target = Path(f"{tmp_path}/{sds_dir}") / file_info.name
    local_target.parent.mkdir(parents=True, exist_ok=True)
    local_target.write_bytes(b"old-bytes")

    server_content = b"server-bytes-new"

    # ensure the stored checksum is different from the local file to force re-download
    file_info.sum_blake3 = "remote-checksum-different"

    def fake_download_file(*args, **kwargs):
        # Accepts either positional or keyword args from the mock and extract the
        # target local path. The mock may be called without `self` in kwargs.
        file_uuid = kwargs.get("file_uuid")
        to_local_path = kwargs.get("to_local_path")
        if to_local_path is None:
            # fall back to positional args if present
            if len(args) == 1:
                to_local_path = args[0]
            elif len(args) > 1:
                to_local_path = args[-1]

            assert to_local_path is not None, (
                "to_local_path not provided to fake_download_file"
            )

        log.debug(
            f"Fake download_file called for UUID {file_uuid} to {to_local_path.name}"  # ty:ignore[possibly-missing-attribute]
        )
        to_local_path.parent.mkdir(parents=True, exist_ok=True)  # ty:ignore[possibly-missing-attribute]
        to_local_path.write_bytes(server_content)  # ty:ignore[possibly-missing-attribute]
        # update the file_info to reflect the new local file and checksum
        file_info.local_path = to_local_path
        file_info.sum_blake3 = file_info.compute_sum_blake3()
        return file_info

    with patch.object(
        Client, "download_file", side_effect=fake_download_file
    ) as patched:
        result = client.download_single_file(
            file_info=file_info,
            to_local_path=tmp_path,
            skip_contents=False,
            overwrite=True,
        )
    # assert that our patched download method was called
    assert patched.called, "download_file was not invoked"

    returned = result()
    assert local_target.read_bytes() == server_content, (
        "Local file content should match server content. "
        f"Got {local_target.read_bytes()}, expected {server_content}"
    )
    assert returned.sum_blake3 == returned.compute_sum_blake3(), (
        "Returned file checksum should match computed checksum."
        f" Got {returned.sum_blake3}, expected {returned.compute_sum_blake3()}"
    )


def test_existing_local_file_identical_checksum_not_redownloaded(
    tmp_path: Path, client: Client
) -> None:
    """When the local file has an identical checksum, it must not be re-downloaded."""

    sds_dir = PurePosixPath("same/checksum")
    file_info = files.generate_sample_file(uuid.uuid4())
    file_info.directory = sds_dir
    file_info.name = "same.txt"

    local_target = Path(f"{tmp_path}/{sds_dir}") / file_info.name
    local_target.parent.mkdir(parents=True, exist_ok=True)
    local_target.write_text("identical content")

    # set file_info to reflect the local content checksum
    file_info.local_path = local_target
    file_info.sum_blake3 = file_info.compute_sum_blake3()

    with patch.object(
        Client,
        "download_file",
        side_effect=AssertionError("download_file should not be called"),
    ):
        result = client.download_single_file(
            file_info=file_info,
            to_local_path=tmp_path,
            skip_contents=False,
            overwrite=True,
        )

    assert result, "Result should not be None"
    assert result() is file_info, "Returned file should be the original file_info"


def test_resolve_dataset_capture_filter_dry_run_disables() -> None:
    active, uuids, dirs = resolve_dataset_capture_filter_params(
        capture_uuids=[uuid.uuid4()],
        top_level_dirs=None,
        dry_run=True,
    )
    assert not active
    assert uuids is None
    assert dirs is None


def test_resolve_dataset_capture_filter_normalizes_top_level_dirs() -> None:
    active, uuids, dirs = resolve_dataset_capture_filter_params(
        capture_uuids=None,
        top_level_dirs=["foo/bar", "/baz/"],
        dry_run=False,
    )
    assert active
    assert uuids is None
    assert dirs == ["/foo/bar", "/baz"]


# ======================================================================
# _normalize_top_level_dir_prefix
# ======================================================================


def test_normalize_top_level_dir_prefix() -> None:
    """Covers _normalize_top_level_dir_prefix edge cases."""
    assert _normalize_top_level_dir_prefix("foo/bar") == "/foo/bar"
    assert _normalize_top_level_dir_prefix("/baz/") == "/baz"
    assert _normalize_top_level_dir_prefix("/") == "/"
    assert _normalize_top_level_dir_prefix("a\\b") == "/a/b"


# ======================================================================
# resolve_dataset_capture_filter_params edge cases
# ======================================================================


def test_resolve_dataset_capture_filter_none_params() -> None:
    """When both captures and dirs are None, filter is not active (line 61)."""
    active, uuids, dirs = resolve_dataset_capture_filter_params(
        capture_uuids=None,
        top_level_dirs=None,
        dry_run=False,
    )
    assert not active
    assert uuids is None
    assert dirs is None


def test_resolve_dataset_capture_filter_empty_collections() -> None:
    """Empty collections produce active filter with empty sets (lines 71-75)."""
    active, uuids, dirs = resolve_dataset_capture_filter_params(
        capture_uuids=[],
        top_level_dirs=[],
        dry_run=False,
    )
    assert active
    assert uuids is not None
    assert len(uuids) == 0
    assert dirs is not None
    assert len(dirs) == 0


def test_resolve_dataset_capture_filter_uuid_str_conversion() -> None:
    """String UUIDs are properly converted to UUID objects (line 71)."""
    uuid_str = "12345678-1234-5678-1234-567812345678"
    active, uuids, _dirs = resolve_dataset_capture_filter_params(
        capture_uuids=[uuid_str],
        top_level_dirs=None,
        dry_run=False,
    )
    assert active
    assert uuids is not None
    assert len(uuids) == 1
    u = next(iter(uuids))
    assert isinstance(u, UUID)
    assert str(u) == uuid_str


# ======================================================================
# Client miscellaneous properties and methods
# ======================================================================


def test_client_str() -> None:
    """Client.__str__ returns a descriptive string (line 159)."""
    client = Client(host="sds-dev.crc.nd.edu")
    assert "sds-dev.crc.nd.edu" in str(client)


def test_verbose_enables_output(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    """Verbose mode produces log output during operations."""
    caplog.set_level(LogLevels.DEBUG)
    client.dry_run = True
    client.verbose = True
    client.get_file(file_uuid=uuid.uuid4())
    assert len(caplog.records) > 0


def test_non_verbose_suppresses_output(
    client: Client, caplog: pytest.LogCaptureFixture
) -> None:
    """Non-verbose mode suppresses verbose log output."""
    caplog.set_level(LogLevels.DEBUG)
    client.dry_run = True
    client.verbose = False
    client.get_file(file_uuid=uuid.uuid4())
    verbose_messages = [r for r in caplog.records if "verbose" in r.message.lower()]
    assert len(verbose_messages) == 0


def test_client_base_url_properties(client: Client) -> None:
    """base_url and base_url_no_port properties (lines 214, 219)."""
    assert client.base_url.startswith("http")
    assert isinstance(client.base_url_no_port, str)


# ======================================================================
# Download method tests
# ======================================================================


def test_download_mutual_exclusion(
    tmp_path: Path,
    client: Client,
) -> None:
    """from_sds_path and files_to_download are mutually exclusive (lines 308-314)."""
    with pytest.raises(ValueError, match="Both a path in the SDS"):
        client.download(
            from_sds_path="/some/path",
            to_local_path=tmp_path,
            files_to_download=[],
        )


def _get_file_download_endpoint(client: Client, file_id: str) -> str:
    """Returns the endpoint for downloading a file's contents."""
    return (
        client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/{file_id}/download/"
    )


@responses.activate
def test_download_single_file_sdserror(
    tmp_path: Path,
    client: Client,
    caplog: pytest.LogCaptureFixture,
    responses: responses.RequestsMock,
) -> None:
    """download_single_file catches SDSError (lines 461-463)."""
    client.dry_run = False
    caplog.set_level(LogLevels.ERROR)
    file_info = files.generate_sample_file(uuid.uuid4())
    file_info.directory = PurePosixPath("remote/dir")
    assert file_info.uuid is not None
    file_id_hex = file_info.uuid.hex

    # File info GET succeeds
    responses.add(
        method=responses.GET,
        url=get_files_endpoint(client) + f"{file_id_hex}/",
        status=200,
        json={
            "uuid": file_id_hex,
            "name": file_info.name,
            "media_type": "text/plain",
            "size": 100,
            "directory": "/remote/dir",
            "permissions": "rw-r--r--",
            "created_at": "2024-12-01T12:00:00Z",
            "updated_at": "2024-12-01T12:00:00Z",
            "expiration_date": "2026-12-01T12:00:00Z",
        },
    )
    # Download GET fails with server error
    responses.add(
        method=responses.GET,
        url=_get_file_download_endpoint(client, file_id_hex),
        status=500,
        json={"detail": "Internal Server Error"},
    )

    result = client.download_single_file(
        file_info=file_info,
        to_local_path=tmp_path,
        skip_contents=False,
        overwrite=False,
    )
    assert not result
    exc = result.exception_or(None)
    assert exc is not None
    assert (
        "500" in str(exc)
        or "Server Error" in str(exc)
        or "Internal Server Error" in str(exc)
    )


def test_download_no_path_no_files(
    tmp_path: Path,
    client: Client,
) -> None:
    """Missing both path and files raises ValueError (lines 369-374)."""
    client.dry_run = False
    with pytest.raises(ValueError, match="Either a path in the SDS"):
        client.download(to_local_path=tmp_path)


# ======================================================================
# download_dataset endpoint tests
# ======================================================================


@pytest.mark.parametrize("uuid_arg", [uuid.uuid4(), str(uuid.uuid4())])
def test_download_dataset_dry_run(
    tmp_path: Path,
    client: Client,
    uuid_arg: uuid.UUID | str,
) -> None:
    """download_dataset works in dry run mode (lines 588-652)."""
    results = client.download_dataset(
        dataset_uuid=uuid_arg,
        to_local_path=tmp_path,
        verbose=False,
    )
    assert len(results) == _DRY_RUN_FILE_COUNT


def test_download_dataset_empty_filters_active(
    tmp_path: Path,
    client: Client,
) -> None:
    """download_dataset with empty filters produces empty file list (lines 604-606).

    When filter_active=True but both uuid_set and dir_prefixes_norm are empty,
    files_to_download is set to an empty list directly.
    """
    client.dry_run = False
    results = client.download_dataset(
        dataset_uuid=uuid.uuid4(),
        to_local_path=tmp_path,
        capture_uuids=[],
        top_level_dirs=[],
        verbose=False,
    )
    assert len(results) == 0


@responses.activate
@pytest.mark.parametrize(
    ("capture_uuids", "top_level_dirs"),
    [
        ([uuid.uuid4()], ["/some/path"]),
        ([uuid.uuid4()], None),
        (None, ["/some/path"]),
    ],
)
def test_download_dataset_filter_branches(
    tmp_path: Path,
    client: Client,
    responses: responses.RequestsMock,
    capture_uuids,
    top_level_dirs,
) -> None:
    """download_dataset filter_active paths with HTTP-level mocking.

    Covers all three branches: both filters active, only uuids, and only dirs.
    """
    client.dry_run = False
    dataset_uuid = uuid.uuid4()
    # Mock the dataset files endpoint to return empty results
    responses.add(
        method=responses.GET,
        url=get_datasets_endpoint(client, dataset_id=dataset_uuid.hex) + "files/",
        status=200,
        json={"count": 0, "results": []},
    )
    results = client.download_dataset(
        dataset_uuid=dataset_uuid,
        to_local_path=str(tmp_path),
        capture_uuids=capture_uuids,
        top_level_dirs=top_level_dirs,
        verbose=False,
    )
    assert len(results) == 0


# ======================================================================
# Dataset read methods with string UUID (lines 662-678)
# ======================================================================


def test_get_dataset_string_uuid(client: Client) -> None:
    """get_dataset accepts a string UUID (lines 662-664)."""
    ds = client.get_dataset(dataset_uuid=str(uuid.uuid4()))
    assert ds.uuid is not None


def test_list_dataset_captures_string_uuid(client: Client) -> None:
    """list_dataset_captures accepts a string UUID (lines 668-670)."""
    result = client.list_dataset_captures(dataset_uuid=str(uuid.uuid4()))
    assert result == []


def test_list_dataset_artifact_files_string_uuid(client: Client) -> None:
    """list_dataset_artifact_files accepts a string UUID (lines 676-678)."""
    result = client.list_dataset_artifact_files(dataset_uuid=str(uuid.uuid4()))
    assert result == []


# ======================================================================
# Upload method tests
# ======================================================================


@responses.activate
def test_upload_capture_sdserror(
    client: Client,
    tmp_path: Path,
    responses: responses.RequestsMock,
) -> None:
    """upload_capture: SDSError during capture creation returns None (lines 872-877)."""
    client.dry_run = False
    local_file = tmp_path / "test_upload.txt"
    local_file.write_text("test content")

    file_id = uuid.uuid4()

    # The resumable upload discovers files in tmp_path (test file + log file).
    # Each file triggers: content-check POST then file-upload POST.
    for _ in range(2):
        # Content check endpoint — file does not exist in tree
        responses.add(
            method=responses.POST,
            url=get_content_check_endpoint(client),
            status=200,
            json={
                "file_contents_exist_for_user": False,
                "file_exists_in_tree": False,
                "user_mutable_attributes_differ": True,
            },
        )
        # File upload endpoint succeeds
        responses.add(
            method=responses.POST,
            url=get_files_endpoint(client),
            status=201,
            json={
                "uuid": file_id.hex,
                "name": "test_upload.txt",
                "media_type": "text/plain",
                "size": local_file.stat().st_size,
                "directory": "/",
                "permissions": "rw-r--r--",
                "created_at": "2024-12-01T12:00:00Z",
                "updated_at": "2024-12-01T12:00:00Z",
                "expiration_date": "2026-12-01T12:00:00Z",
            },
        )
    # Capture creation endpoint fails
    responses.add(
        method=responses.POST,
        url=get_captures_endpoint(client),
        status=400,
        json={"detail": "Capture failed"},
    )

    result = client.upload_capture(
        local_path=tmp_path,
        sds_path="/",
        capture_type=CaptureType.DigitalRF,
        verbose=False,
        raise_on_error=False,
    )
    assert result is None


def test_upload_multichannel_drf_capture_empty_channels(
    client: Client,
    tmp_path: Path,
) -> None:
    """upload_multichannel with empty channels returns [] (lines 954-956)."""
    # Create a file so the resumable upload discovers something
    local_file = tmp_path / "test_upload.txt"
    local_file.write_text("test content")

    client.dry_run = True
    results = client.upload_multichannel_drf_capture(
        local_path=tmp_path,
        sds_path="/",
        channels=[],
        verbose=False,
    )
    assert results is not None
    assert len(results) == 0


def test_upload_multichannel_drf_capture_dry_run(
    client: Client,
    tmp_path: Path,
) -> None:
    """upload_multichannel works end-to-end in dry run mode (lines 937-987)."""
    channels = ["chan1", "chan2"]
    # Create a file so the resumable upload discovers something
    local_file = tmp_path / "test_upload.txt"
    local_file.write_text("test content")

    client.dry_run = True
    results = client.upload_multichannel_drf_capture(
        local_path=tmp_path,
        sds_path="/",
        channels=channels,
        verbose=False,
    )
    assert results is not None
    assert len(results) == len(channels)
    for capture in results:
        assert capture.capture_type == CaptureType.DigitalRF


# ======================================================================
# _handle_existing_capture_error tests (lines 889-902)
#
# These test a private utility method directly because triggering the
# specific error-handling branches through the public API would require
# complex HTTP mocking with no additional behavioral coverage benefit.
# ======================================================================


def test_handle_existing_capture_error_non_capture_error(client: Client) -> None:
    """Non-CaptureError returns (False, None) (lines 889-890)."""
    err = SDSError("Some other error")
    handled, capture = client._handle_existing_capture_error(err)  # noqa: SLF001
    assert not handled
    assert capture is None


def test_handle_existing_capture_error_no_existing_uuid(client: Client) -> None:
    """CaptureError without existing UUID returns (False, None) (lines 892-894)."""
    err = CaptureError("Generic capture error without UUID info")
    handled, capture = client._handle_existing_capture_error(err)  # noqa: SLF001
    assert not handled
    assert capture is None


def test_handle_existing_capture_error_read_fails(client: Client) -> None:
    """CaptureError with existing UUID, but read fails (lines 899-900)."""
    err = CaptureError(
        "drf_unique_channel_and_tld another capture: "
        "12345678-1234-5678-1234-567812345678"
    )
    with patch.object(client.captures, "read", side_effect=SDSError("Read failed")):
        handled, capture = client._handle_existing_capture_error(err)  # noqa: SLF001
    assert not handled
    assert capture is None


def test_download_byte_progress_credits_skipped_content(
    client: Client, tmp_path: Path
) -> None:
    """Progress should reach file totals when content transfer is skipped."""
    file_info = files.generate_sample_file(uuid.uuid4())
    file_info.size = 1000
    bytes_downloaded_shared: list[int] = [0]
    prog_bar = MagicMock()

    with (
        patch.object(
            Client,
            "download_single_file",
            return_value=Result(value=file_info),
        ),
        patch("spectrumx.client.get_prog_bar", return_value=prog_bar),
    ):
        results = client._download_files_with_byte_progress(  # noqa: SLF001
            files_to_download=[file_info],
            total_bytes_total=file_info.size,
            to_local_path=tmp_path,
            skip_contents=True,
            overwrite=False,
            verbose=True,
            prefix="Downloading",
            total_files=1,
            period=30.0,
            bytes_downloaded_shared=bytes_downloaded_shared,
        )

    assert len(results) == 1
    assert results[0]
    assert bytes_downloaded_shared[0] == file_info.size
    prog_bar.update.assert_called_once_with(file_info.size)


def test_download_byte_progress_credits_partial_stream(
    client: Client, tmp_path: Path
) -> None:
    """Progress should include both streamed and unstreamed bytes per file."""
    file_info = files.generate_sample_file(uuid.uuid4())
    file_info.size = 1000
    bytes_downloaded_shared: list[int] = [0]

    def fake_download_single_file(*, progress_callback=None, **kwargs):
        if progress_callback is not None:
            progress_callback(400)
        return Result(value=file_info)

    with patch.object(
        Client,
        "download_single_file",
        side_effect=fake_download_single_file,
    ):
        client._download_files_with_byte_progress(  # noqa: SLF001
            files_to_download=[file_info],
            total_bytes_total=file_info.size,
            to_local_path=tmp_path,
            skip_contents=False,
            overwrite=True,
            verbose=True,
            prefix="Downloading",
            total_files=1,
            period=30.0,
            bytes_downloaded_shared=bytes_downloaded_shared,
        )

    assert bytes_downloaded_shared[0] == file_info.size
