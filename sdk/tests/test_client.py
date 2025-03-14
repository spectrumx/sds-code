"""Tests for the client module."""

import re
from enum import IntEnum
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any
from unittest.mock import patch

import pytest
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.config import SDSConfig
from spectrumx.config import _cfg_name_lookup  # pyright: ignore[reportPrivateUsage]
from spectrumx.models.files import File
from spectrumx.ops import files

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
