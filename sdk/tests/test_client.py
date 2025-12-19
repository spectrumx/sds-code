"""Tests for the client module."""

import re
import uuid
from enum import IntEnum
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from unittest.mock import patch

import pytest
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.config import SDSConfig
from spectrumx.config import _cfg_name_lookup
from spectrumx.models.files import File
from spectrumx.ops import files

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

log.trace("Placeholder log avoid reimporting or resolving unused import warnings.")


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

    assert "file missing" in caplog.text.lower()


def test_load_config_file_found(caplog: pytest.LogCaptureFixture) -> None:
    """A valid env file must be found and loaded."""

    filename = "existing.env"
    existing_file = Path(filename)
    existing_file.touch()
    caplog.set_level(LogLevels.DEBUG)
    SDSConfig(env_file=existing_file, verbose=True)

    pattern = f"found.*{filename}".lower()
    assert re.search(pattern, caplog.text.lower())
    existing_file.unlink()


def test_load_config_from_args(sample_config: dict[str, Any]) -> None:
    """Ensures loading config from arguments works."""

    config = SDSConfig(env_file=Path(".env.example"), env_config=sample_config)

    for key, value in sample_config.items():
        norm_key = (
            _cfg_name_lookup[key.lower()].attr_name
            if key.lower() in _cfg_name_lookup
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

    assert "api_key" in all_outputs
    assert sample_config["SDS_SECRET_TOKEN"] not in all_outputs


def test_warning_for_unrecognized_config(
    sample_config: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """A warning must be logged for unrecognized configuration."""

    unknown_attr = "UNRECOGNIZED_CONFIG"
    sample_config[unknown_attr] = "value"
    caplog.set_level(LogLevels.WARNING)
    SDSConfig(env_file=Path(".env.example"), env_config=sample_config)

    assert "not recognized" in caplog.text.lower()
    assert unknown_attr in caplog.text


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
    assert (
        "Dry-run enabled: no SDS requests will be made or files written." in caplog.text
    )
    assert len(results) == expected_length
    assert len(successful) == expected_length
    assert all(file_obj.is_sample for file_obj in successful), (
        "All files should be sample files in dry-run."
    )


def test_download_fails_for_invalid_files(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
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
        _ = capsys.readouterr()
        results = client.download(from_sds_path=sds_path, to_local_path=local_path)
        assert len(results) == target_num_files, "Three files should be generated"

        captured = capsys.readouterr()
        log.debug(captured.err)
        assert "simulating download" in captured.err
        # assert "Skipping local file" in captured.err
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
        result = client._download_single_file(
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
        result = client._download_single_file(
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
        result = client._download_single_file(
            file_info=file_info,
            to_local_path=tmp_path,
            skip_contents=False,
            overwrite=True,
        )

    assert result, "Result should not be None"
    assert result() is file_info, "Returned file should be the original file_info"
