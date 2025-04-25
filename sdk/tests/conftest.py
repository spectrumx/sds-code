"""Common test fixtures and utilities for the SDS SDK."""

import os
import random
import sys
import uuid
from collections.abc import Generator
from pathlib import Path
from typing import Any

import pytest
from loguru import logger as log
from spectrumx import enable_logging
from spectrumx.client import Client
from spectrumx.gateway import API_TARGET_VERSION
from spectrumx.models.files import File
from spectrumx.ops import files
from spectrumx.utils import get_random_line

# better traceback formatting with rich, if available
try:
    from rich import traceback

    traceback.install()
except ImportError:
    log.warning("Install rich for better tracebacks")

enable_logging()

# Platform Specific Testing
PLATFORMS = {"darwin", "linux", "win32"}


def pytest_runtest_setup(item) -> None:
    supported_platforms = PLATFORMS.intersection(
        mark.name for mark in item.iter_markers()
    )
    plat = sys.platform
    if supported_platforms and plat not in supported_platforms:
        pytest.skip(f"cannot run on platform {plat}")


# ==== fixtures


@pytest.fixture
def client() -> Client:
    """Fixture to create a Client instance for testing."""
    return Client(host="sds-dev.crc.nd.edu")


@pytest.fixture
def sample_config() -> dict[str, Any]:
    """Fixture to create a sample configuration."""
    return {
        "SDS_SECRET_TOKEN": "12345",
        "HTTP_TIMEOUT": 42,
        "SDS_HOST": "sds-test.example.com",
    }


@pytest.fixture
def temp_file_empty(tmp_path: Path) -> Path:
    """Fixture to create a temporary file for testing."""
    file_path = tmp_path / "empty_test_file.txt"
    file_path.touch()
    return file_path


@pytest.fixture
def temp_file_with_text_contents(tmp_path: Path) -> Generator[Path]:
    """Fixture for a file with contents."""
    file_path = (
        tmp_path / f"test_file_{get_random_line(6, include_punctuation=False)}.txt"
    )
    # generate random string to change checksums every time
    with file_path.open("w", encoding="utf-8") as file_handle:
        file_handle.writelines(file_content_generator())

    yield file_path

    file_path.unlink(missing_ok=True)


@pytest.fixture
@pytest.mark.slow
def temp_large_binary_file(
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Generator[Path]:
    """Fixture to create a temporary large binary file."""
    target_size_mb = (
        request.param.get("size_mb", None) if hasattr(request, "param") else None
    )
    if target_size_mb is None:
        target_size_mb = random.randint(10, 20)  # noqa: S311
    log.warning(f"Creating a large binary file of {target_size_mb:,} MB.")
    large_binary_file = tmp_path / "large_binary_file"
    byte_generator = random_bytes_generator(1024 * 1024 * target_size_mb)
    with large_binary_file.open("wb") as f_ptr:
        for chunk in byte_generator:
            f_ptr.write(chunk)

    yield large_binary_file

    large_binary_file.unlink(missing_ok=True)


@pytest.fixture
def temp_file_tree(
    tmp_path: Path,
    num_dirs: int = 3,
    num_files_per_dir: int = 3,
) -> Generator[Path]:
    """Fixture to create a temporary directory with files in subdirs."""

    _total_num_files = num_dirs * num_files_per_dir
    _all_created_files: list[Path] = []
    _all_created_dirs: list[Path] = []
    extension: str = "txt"

    for dir_idx in range(num_dirs):
        subdir = tmp_path / f"subdir_{dir_idx}"
        subdir.mkdir(exist_ok=True)
        _all_created_dirs.append(subdir)
        for file_sub_idx in range(num_files_per_dir):
            file_path = subdir / f"test_file_{file_sub_idx}.{extension}"
            _all_created_files.append(file_path)
            with file_path.open("w", encoding="utf-8") as file_handle:
                file_handle.writelines(file_content_generator())
    assert len(_all_created_files) == _total_num_files

    yield tmp_path

    # cleanup
    for file_path in _all_created_files:
        file_path.unlink(missing_ok=True)
    for dir_path in _all_created_dirs:
        dir_path.rmdir()


class FakeFileFactory:
    """Say that three times fast."""

    def __init__(
        self, num_files: int, *, tmp_path: Path, create_local: bool = False
    ) -> None:
        self.num_files: int = num_files
        self.create_local: bool = create_local
        self.fake_files: list[File] = []
        self.tmp_path: Path = tmp_path
        self.value: list[File] = []

    def _inner_loop(self) -> Generator[File, None, list[File]]:
        """Inner loop to generate fake files."""
        for _ in range(self.num_files):
            file_obj = files.generate_sample_file(uuid.uuid4())
            if self.create_local:
                file_obj.local_path = self.tmp_path / f"{file_obj.name}"
                file_obj.local_path.touch()
            self.fake_files.append(file_obj)
            yield file_obj
        self.value = self.fake_files
        return self.value

    def __iter__(self) -> Generator[File, None, list[File]]:
        """Sets self.value properly when this generator is nested."""
        self.value = yield from self._inner_loop()
        return self.value


@pytest.fixture
# yes, this returns a generator of a generator
def fake_files(
    request: pytest.FixtureRequest, tmp_path: Path
) -> Generator[FakeFileFactory]:
    """Fixture to create a list of fake files."""

    _file_count = request.param.get("file_count", 4)
    _create_local = request.param.get("create_local", False)

    # yield to test
    file_gen = FakeFileFactory(
        num_files=_file_count, create_local=_create_local, tmp_path=tmp_path
    )
    yield file_gen

    # get returned list of files for cleanup
    fake_files: list[File] = file_gen.value
    assert isinstance(fake_files, list), (
        "Expected a list of File instances as generator value"
    )

    # cleanup
    log.error(f"Cleaning up {len(fake_files)} fake files.")
    for file_obj in fake_files:
        assert isinstance(file_obj, File), "Expected a File instance"
        if file_obj.local_path:
            file_obj.local_path.unlink(missing_ok=True)


# ==== helpers


def file_content_generator(
    num_lines: int = 100, chars_per_line: int = 80
) -> Generator[str]:
    """Generator for file content."""
    for _current_line in range(num_lines):
        random_line = get_random_line(chars_per_line)
        yield f"{random_line}\n"


def get_captures_endpoint(
    client: Client,
    capture_id: str | None = None,
) -> str:
    """Returns the endpoint for captures."""
    base_endpoint = client.base_url + f"/api/{API_TARGET_VERSION}/assets/captures/"
    if capture_id:
        return base_endpoint + f"{capture_id}/"
    return base_endpoint


def get_files_endpoint(client: Client) -> str:
    """Returns the endpoint for the files API, with trailing slash."""
    return client.base_url + f"/api/{API_TARGET_VERSION}/assets/files/"


def get_content_check_endpoint(client: Client) -> str:
    """Returns the endpoint for the content check API."""
    return (
        client.base_url
        + f"/api/{API_TARGET_VERSION}/assets/utils/check_contents_exist/"
    )


def random_bytes_generator(size: int, chunk: int = 1024) -> Generator[bytes]:
    """Generates random binary data for tests."""
    for _ in range(size // chunk):
        yield os.urandom(chunk)
    yield os.urandom(size % chunk)
