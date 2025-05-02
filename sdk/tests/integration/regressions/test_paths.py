"""Regression tests for handling paths."""

from pathlib import Path
from pathlib import PurePosixPath

import pytest
from loguru import logger as log
from spectrumx.client import Client
from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureType
from spectrumx.utils import get_random_line

from tests.integration.conftest import PassthruEndpoints
from tests.integration.test_captures import drf_channel
from tests.integration.test_captures import load_rh_data


@pytest.fixture
def valid_sds_paths() -> list[str | PurePosixPath]:
    """Generates a list of valid SDS paths for testing."""
    random_subdir_name = get_random_line(10, include_punctuation=False)
    sds_paths_absolute: list[str | PurePosixPath] = [
        f"/{random_subdir_name}/path",
        f"/{random_subdir_name}/path/",
        f"/{random_subdir_name}/path/file.txt",
        f"/{random_subdir_name}/path/file.txt/extra/",
    ]
    sds_paths_relative: list[str | PurePosixPath] = [
        f"{random_subdir_name}/path",
        f"{random_subdir_name}/path/",
        f"{random_subdir_name}/path/file.txt",
        f"{random_subdir_name}/path/file.txt/extra/",
    ]
    sds_paths_relative += [PurePosixPath(p) for p in sds_paths_relative]
    sds_paths_absolute = [PurePosixPath(p) for p in sds_paths_absolute]
    valid_sds_paths: list[str | PurePosixPath] = sds_paths_absolute + sds_paths_relative
    return valid_sds_paths


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_meta_download_or_upload(),
            *PassthruEndpoints.file_content_download(),
        ]
    ],
    indirect=True,
)
def test_paths_sds_download_dir(
    integration_client: Client,
    tmp_path: Path,
    valid_sds_paths: list[str | PurePosixPath],
) -> None:
    """Client and server should accept various SDS path styles for downloads."""

    integration_client.dry_run = False
    for idx, sds_path in enumerate(valid_sds_paths):
        local_path = tmp_path / f"test_{idx}/"
        _results = integration_client.download(
            from_sds_path=sds_path,
            to_local_path=local_path,
            verbose=True,
        )
        assert all(_results), f"Failed to download {sds_path} to {local_path}"
        # since no file was uploaded to this random sds location, the local
        # path will be empty and we can use rmdir() to remove it: we're just
        # making sure the server accepts the arguments, not testing the downloads
        local_path.rmdir()


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
@pytest.mark.usefixtures("_without_responses")
@pytest.mark.parametrize(
    "_without_responses",
    argvalues=[
        [
            *PassthruEndpoints.file_content_checks(),
            *PassthruEndpoints.file_content_download(),
            *PassthruEndpoints.file_meta_download_or_upload(),
            *PassthruEndpoints.file_uploads(),
        ]
    ],
    indirect=True,
)
def test_paths_sds_upload_and_download_file(
    integration_client: Client,
    temp_file_with_text_contents: Path,
    tmp_path: Path,
    valid_sds_paths: list[str | PurePosixPath],
) -> None:
    """Client and server should accept various SDS path styles for single file."""

    # this makes several requests, so we silence some of the output
    # comment this out if the test is failing
    integration_client.verbose = False

    assert len(valid_sds_paths) > 0, "No valid SDS paths provided"
    for idx, sds_path in enumerate(valid_sds_paths):
        log.debug(f"Testing up/list/down file path {type(sds_path)!s:>40} '{sds_path}'")
        integration_client.upload_file(
            local_file=temp_file_with_text_contents,
            sds_path=sds_path,
        )
        file_list = integration_client.list_files(
            sds_path=sds_path.parent
            if isinstance(sds_path, Path)
            else str(Path(sds_path).parent),
            verbose=False,
        )
        assert len(file_list) > 0, f"Failed to list files in '{sds_path}'"
        for file_instance in file_list:
            local_path = tmp_path / f"test_{idx}.txt"
            my_file = integration_client.download_file(
                file_instance=file_instance,
                to_local_path=local_path,
            )
            assert my_file.is_local, f"Failed to download {sds_path} to '{local_path}'"
            # since no file was uploaded to this random sds location, the local
            # path will be empty and we can use unlink() to remove it: we're just
            # making sure the server accepts the arguments, not testing the downloads
            local_path.unlink()
            break


@pytest.mark.integration
@pytest.mark.usefixtures("_integration_setup_teardown")
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
def test_paths_sds_capture_ops(
    integration_client: Client,
    valid_sds_paths: list[str | PurePosixPath],
    rh_sample_top_level_dir: Path,
    drf_sample_top_level_dir: Path,
) -> None:
    """Client and server should accept various SDS path styles for handling captures."""

    # this test makes several requests, so we silence some of the output
    integration_client.verbose = False

    # cleanup all captures
    cleanup_captures(
        integration_client=integration_client,
        captures_created=integration_client.captures.listing(),
    )

    # ARRANGE a new directory to upload as capture
    log.debug("Testing SDS paths for DRF capture uploads")
    captures_created: list[Capture] = []
    try:
        for sds_path in valid_sds_paths:
            random_suffix = get_random_line(10, include_punctuation=False)
            sds_path_random = (
                sds_path / random_suffix
                if isinstance(sds_path, PurePosixPath)
                else _append_suffix(sds_path, suffix=random_suffix)
            )
            log.debug(
                "Testing 'upload capture' path "
                f"{type(sds_path_random)!s:>40} '{sds_path_random}'"
            )
            capture = integration_client.upload_capture(
                local_path=drf_sample_top_level_dir,
                sds_path=sds_path_random,
                capture_type=CaptureType.DigitalRF,
                channel=drf_channel,
                verbose=False,
                warn_skipped=False,
            )
            assert capture is not None, (
                f"Failed to upload capture to '{sds_path_random}'"
            )
            captures_created.append(capture)
            assert str(capture.top_level_dir) == _normalized_top_level_dir(
                sds_path_random
            ), f"Capture top level dir '{capture.top_level_dir}' != '{sds_path_random}'"

    finally:
        cleanup_captures(
            integration_client=integration_client,
            captures_created=captures_created,
        )

    # recreate them at the same SDS paths as RadioHound captures
    log.debug("Testing SDS paths for RH capture uploads")
    rh_data = load_rh_data(rh_sample_top_level_dir)

    for sds_path in valid_sds_paths:
        random_suffix = get_random_line(10, include_punctuation=False)
        sds_path_random = (
            sds_path / random_suffix
            if isinstance(sds_path, PurePosixPath)
            else _append_suffix(sds_path, suffix=random_suffix)
        )
        log.debug(
            "Testing 'upload capture' path "
            f"{type(sds_path_random)!s:>40} '{sds_path_random}'"
        )
        capture = integration_client.upload_capture(
            local_path=rh_sample_top_level_dir,
            sds_path=sds_path_random,
            capture_type=CaptureType.RadioHound,
            scan_group=rh_data.get("scan_group"),
            verbose=False,
            warn_skipped=False,
        )
        assert capture is not None, f"Failed to upload capture to '{sds_path_random}'"
        assert capture.uuid is not None, f"Capture UUID is None for '{sds_path_random}'"
        assert str(capture.top_level_dir) == _normalized_top_level_dir(
            sds_path_random
        ), f"Capture top level dir '{capture.top_level_dir}' != '{sds_path_random}'"

        # cleanup
        integration_client.captures.delete(capture_uuid=capture.uuid)


def cleanup_captures(
    integration_client: Client, captures_created: list[Capture]
) -> None:
    """Clean up captures created during the test."""
    for capture in captures_created:
        log.debug(f"Deleting capture {capture.uuid}")
        if capture.uuid is None:
            log.error("Capture UUID is None")
            continue
        integration_client.captures.delete(capture_uuid=capture.uuid)


def _append_suffix(target_path: str, suffix: str) -> str:
    """Append a suffix to the target path."""
    if not target_path.endswith("/"):
        target_path += "/"
    target_path += suffix
    return target_path


def _normalized_top_level_dir(sds_path: str | PurePosixPath) -> str:
    """Normalize the top level directory path."""
    if isinstance(sds_path, PurePosixPath):
        sds_path = str(sds_path)
    if not isinstance(sds_path, str):
        msg = f"Expected str or PurePosixPath, got {type(sds_path)}"
        raise TypeError(msg)

    # must start with a slash
    if not sds_path.startswith("/"):
        sds_path = "/" + sds_path

    # must NOT end with a slash
    return sds_path.rstrip("/")
