"""Tests for the uploads API utilities — UploadWorkload state machine."""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import Mock
from unittest.mock import patch

import pytest
from spectrumx.api.uploads import SkippedUpload
from spectrumx.api.uploads import UploadWorkload
from spectrumx.api.uploads import create_file_instance
from spectrumx.errors import Result
from spectrumx.errors import UploadError
from spectrumx.models.files.file import File
from spectrumx.ops import files as file_ops
from tqdm import tqdm

if TYPE_CHECKING:
    from collections.abc import Callable

    from spectrumx.client import Client

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false


@pytest.fixture
def temp_text_file(tmp_path: Path) -> tuple[Path, Path]:
    """Create a temporary directory containing one text file."""
    root = tmp_path / "upload_root"
    nested_dir = root / "nested"
    nested_dir.mkdir(parents=True, exist_ok=True)
    candidate = nested_dir / "example.txt"
    candidate.write_text("hello world", encoding="utf-8")

    return root, candidate


@pytest.fixture
def temp_file_tree(tmp_path: Path) -> tuple[Path, list[Path]]:
    """Create a directory with multiple nested files."""
    root = tmp_path / "upload_root"
    root.mkdir()

    files_created: list[Path] = []

    for dir_idx in range(3):
        subdir = root / f"dir_{dir_idx}"
        subdir.mkdir()
        for file_idx in range(2):
            file_path = subdir / f"file_{file_idx}.txt"
            file_path.write_text(f"content {dir_idx}-{file_idx}", encoding="utf-8")
            files_created.append(file_path)

    return root, files_created


def _create_mock_file(
    name: str = "test_file.txt",
    size: int = 1024,
    local_path: Path | None = None,
    file_uuid: uuid.UUID | None = None,
) -> File:
    """Helper to create a mock File with required attributes."""
    file_mock = MagicMock(spec=File)
    file_mock.name = name
    file_mock.size = size
    file_mock.directory = PurePosixPath("test_dir")
    file_mock.local_path = local_path or Path(name)
    file_mock.uuid = file_uuid or uuid.UUID(int=0)
    file_mock.compute_sum_blake3.return_value = f"checksum_{name}"
    return file_mock


@pytest.fixture
def mock_file(tmp_path: Path) -> File:
    """Create a mock File instance."""
    return _create_mock_file(local_path=tmp_path / "test_file.txt")


@pytest.fixture
def upload_workload(tmp_path: Path, client: Client) -> UploadWorkload:
    """Create an UploadWorkload instance for testing."""
    root = tmp_path / "upload_root"
    root.mkdir()
    uw = UploadWorkload(
        client=client,
        local_root=root,
        sds_path=PurePosixPath("/"),
        max_concurrent_uploads=2,
    )
    assert uw._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    return uw


def test_create_file_instance(temp_text_file: tuple[Path, Path]) -> None:
    """Test that create_file_instance builds a File model for a local file."""
    root, candidate = temp_text_file

    file_model = create_file_instance(root=root, candidate=candidate)

    assert file_model.name == candidate.name
    assert file_model.local_path == candidate
    assert file_model.directory == PurePosixPath("nested")
    assert file_model.size == candidate.stat().st_size
    assert file_model.media_type == "text/plain"


def test_create_file_instance_root_level_file(tmp_path: Path) -> None:
    """Test create_file_instance for a file at root level."""
    root = tmp_path / "root"
    root.mkdir()
    file_path = root / "test.txt"
    file_path.write_text("test", encoding="utf-8")

    file_model = create_file_instance(root=root, candidate=file_path)

    assert file_model.directory == PurePosixPath(".")


def test_create_file_instance_deeply_nested(tmp_path: Path) -> None:
    """Test create_file_instance for deeply nested files."""
    root = tmp_path / "root"
    nested_path = root / "a" / "b" / "c"
    nested_path.mkdir(parents=True)
    file_path = nested_path / "deep.txt"
    file_path.write_text("deep content", encoding="utf-8")

    file_model = create_file_instance(root=root, candidate=file_path)

    assert file_model.directory == PurePosixPath("a/b/c")
    assert file_model.name == "deep.txt"


def test_upload_workload_initialization(tmp_path: Path, client: Client) -> None:
    """Test UploadWorkload initializes with correct defaults."""

    default_max_concurrent_uploads = 5

    root = tmp_path / "root"
    root.mkdir()

    workload = UploadWorkload(
        client=client,
        local_root=root,
    )

    assert workload.local_root == root, "Expected local_root to match root"
    assert workload.sds_path == PurePosixPath("/"), "Expected default sds_path to be /"
    assert workload.max_concurrent_uploads == default_max_concurrent_uploads, (
        "Expected max_concurrent_uploads to match default"
    )
    assert workload.total_files == 0, "Expected total_files to be 0 initially"
    assert workload.total_bytes == 0, "Expected total_bytes to be 0 initially"


def test_upload_workload_with_custom_parameters(tmp_path: Path, client: Client) -> None:
    """Test UploadWorkload initialization with custom parameters."""
    root = tmp_path / "root"
    root.mkdir()

    max_concurrent_uploads = 10

    workload = UploadWorkload(
        client=client,
        local_root=root,
        sds_path=PurePosixPath("/custom/path"),
        max_concurrent_uploads=max_concurrent_uploads,
    )

    assert workload.sds_path == PurePosixPath("/custom/path"), (
        "Expected custom sds_path"
    )
    assert workload.max_concurrent_uploads == max_concurrent_uploads, (
        "Expected custom max_concurrent_uploads"
    )


def test_upload_workload_alias_population(tmp_path: Path, client: Client) -> None:
    """Test UploadWorkload respects local_path alias."""
    root = tmp_path / "root"
    root.mkdir()

    workload = UploadWorkload(
        client=client,
        local_root=root,
    )

    assert workload.local_root == root, "Expected local_root to match root"


@pytest.mark.anyio
async def test_register_discovered_file_updates_all_state(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _register_discovered_file updates discovered, pending, and total_bytes."""
    initial_bytes = upload_workload.total_bytes

    await upload_workload._register_discovered_file(mock_file)

    assert mock_file in upload_workload.fq_discovered, (
        "Expected mock_file in discovered files"
    )
    assert mock_file in upload_workload.fq_pending, (
        "Expected mock_file in pending files"
    )
    assert upload_workload.total_bytes == initial_bytes + mock_file.size, (
        "Expected total_bytes to increase by mock_file.size"
    )
    assert upload_workload.total_files == 1, (
        "Expected total_files to be 1 after registration"
    )


@pytest.mark.anyio
async def test_register_multiple_files_accumulates_bytes(
    upload_workload: UploadWorkload,
) -> None:
    """Test that registering multiple files accumulates total_bytes correctly."""
    total_num_files = 3
    file_size_bytes = 1024
    files = [MagicMock(spec=File, size=file_size_bytes) for _ in range(total_num_files)]

    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    assert upload_workload.total_bytes == file_size_bytes * total_num_files, (
        "Expected total_bytes to be sum of all file sizes"
    )
    assert upload_workload.total_files == total_num_files, (
        "Expected total_files to match registered count"
    )


@pytest.mark.anyio
async def test_add_skipped_records_skipped_files(
    upload_workload: UploadWorkload,
) -> None:
    """Test that _add_skipped correctly stores skipped files."""
    path = Path("/tmp/test.txt")  # noqa: S108
    reasons = ("reason1", "reason2")
    skipped = SkippedUpload(path=path, reasons=reasons)

    await upload_workload._add_skipped(skipped)

    assert len(upload_workload.fq_skipped) == 1, "Expected exactly 1 skipped file"
    assert upload_workload.fq_skipped[0].path == path, (
        "Expected skipped file path to match"
    )
    assert upload_workload.fq_skipped[0].reasons == reasons, (
        "Expected skipped file reasons to match"
    )


@pytest.mark.anyio
async def test_acquire_next_file_moves_to_in_progress(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _acquire_next_file moves file from pending to in-progress."""
    await upload_workload._register_discovered_file(mock_file)

    acquired = await upload_workload._acquire_next_file()

    assert acquired == mock_file, "Expected acquired file to match mock_file"
    assert mock_file not in upload_workload.fq_pending, (
        "Expected mock_file removed from pending"
    )
    assert mock_file in upload_workload.fq_in_progress, (
        "Expected mock_file in in_progress"
    )


@pytest.mark.anyio
async def test_acquire_next_file_returns_none_when_empty(
    upload_workload: UploadWorkload,
) -> None:
    """Test _acquire_next_file returns None when no pending files."""
    result = await upload_workload._acquire_next_file()

    assert result is None, "Expected None when no pending files"


@pytest.mark.anyio
async def test_acquire_next_file_fifo_order(
    upload_workload: UploadWorkload,
) -> None:
    """Test _acquire_next_file maintains FIFO order."""
    files = [MagicMock(spec=File, size=100, name=f"file_{i}") for i in range(3)]

    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    for expected_file in files:
        acquired = await upload_workload._acquire_next_file()
        assert acquired == expected_file, "Expected FIFO order for acquired files"


@pytest.mark.anyio
async def test_mark_completed_transitions_file_state(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_completed removes from in_progress and adds to completed."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    result = Result(value=mock_file)
    await upload_workload._mark_completed_result(successful_result=result)

    assert mock_file not in upload_workload.fq_in_progress, (
        "Expected mock_file removed from in_progress"
    )
    assert mock_file in upload_workload.fq_completed, (
        "Expected mock_file in completed files"
    )


@pytest.mark.anyio
async def test_mark_completed_prevents_duplicates(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_completed prevents adding the same file twice."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    result = Result(value=mock_file)
    await upload_workload._mark_completed_result(successful_result=result)

    assert upload_workload.fq_completed.count(mock_file) == 1, (
        "Expected mock_file to appear exactly once in completed"
    )


@pytest.mark.anyio
async def test_mark_failed_transitions_file_state(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_failed removes from in_progress and adds to failed."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    await upload_workload._mark_failed_file(mock_file, reason="test error")

    assert mock_file not in upload_workload.fq_in_progress, (
        "Expected mock_file removed from in_progress after failure"
    )
    assert len(upload_workload.fq_failed) == 1, "Expected exactly 1 failed file"
    assert upload_workload.fq_failed[0].sds_file == mock_file, (
        "Expected failed file to reference mock_file"
    )
    assert upload_workload.fq_failed[0].reason == "test error", (
        "Expected failure reason to match"
    )


@pytest.mark.anyio
async def test_mark_failed_with_none_reason(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_failed handles None reason gracefully."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    await upload_workload._mark_failed_file(mock_file, reason=None)

    assert len(upload_workload.fq_failed) == 1, "Expected exactly 1 failed file"
    assert upload_workload.fq_failed[0].reason is None, (
        "Expected failure reason to be None"
    )


@pytest.mark.anyio
async def test_mark_failed_creates_upload_error(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_failed creates UploadError with correct structure."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    reason_text = "network timeout"
    await upload_workload._mark_failed_file(mock_file, reason=reason_text)

    error = upload_workload.fq_failed[0]
    assert isinstance(error, UploadError), "Expected error to be UploadError instance"
    assert error.sds_file == mock_file, "Expected error to reference mock_file"
    assert error.reason == reason_text, "Expected error reason to match"


@pytest.mark.anyio
async def test_reset_progress_preserves_discovered_files(
    upload_workload: UploadWorkload,
) -> None:
    """Test _reset_progress keeps discovered files intact."""
    num_files = 3
    files = [MagicMock(spec=File, size=100) for _ in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    await upload_workload._reset_progress()

    assert upload_workload.fq_discovered == files, (
        "Expected discovered files preserved after reset"
    )
    assert len(upload_workload.fq_pending) == num_files, (
        "Expected pending files repopulated after reset"
    )


@pytest.mark.anyio
async def test_reset_progress_repopulates_pending(
    upload_workload: UploadWorkload,
) -> None:
    """Test _reset_progress copies discovered files back into pending."""
    files = [MagicMock(spec=File, size=100) for _ in range(3)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    await upload_workload._acquire_next_file()
    await upload_workload._reset_progress()

    assert set(upload_workload.fq_pending) == set(files), (
        "Expected pending files to match discovered files"
    )


@pytest.mark.anyio
async def test_reset_progress_clears_runtime_buffers(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _reset_progress clears in_progress, completed, and failed."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()
    result = Result(value=mock_file)
    await upload_workload._mark_completed_result(result)

    await upload_workload._reset_progress()

    assert len(upload_workload.fq_in_progress) == 0, (
        "Expected in_progress to be cleared"
    )
    assert len(upload_workload.fq_completed) == 0, "Expected completed to be cleared"
    assert len(upload_workload.fq_failed) == 0, "Expected failed to be cleared"


@pytest.mark.anyio
async def test_reset_state_clears_all_buffers(
    upload_workload: UploadWorkload,
) -> None:
    """Test _reset_state completely empties all file queues."""
    files = [MagicMock(spec=File, size=100) for _ in range(3)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    await upload_workload._reset_state()

    assert len(upload_workload.fq_discovered) == 0, "Expected discovered to be cleared"
    assert len(upload_workload.fq_pending) == 0, "Expected pending to be cleared"
    assert len(upload_workload.fq_in_progress) == 0, (
        "Expected in_progress to be cleared"
    )
    assert len(upload_workload.fq_completed) == 0, "Expected completed to be cleared"
    assert len(upload_workload.fq_failed) == 0, "Expected failed to be cleared"
    assert len(upload_workload.fq_skipped) == 0, "Expected skipped to be cleared"


@pytest.mark.anyio
async def test_reset_state_resets_total_bytes(
    upload_workload: UploadWorkload,
) -> None:
    """Test _reset_state resets total_bytes to 0."""
    num_files = 3
    file_size_bytes = 100
    files = [MagicMock(spec=File, size=file_size_bytes) for _ in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    assert upload_workload.total_bytes == file_size_bytes * num_files

    await upload_workload._reset_state()

    assert upload_workload.total_bytes == 0, "Expected total_bytes to be 0 after reset"


def test_total_files_property(upload_workload: UploadWorkload) -> None:
    """Test total_files returns correct count of discovered files."""
    assert upload_workload.total_files == 0, (
        "Expected total_files to be 0 for empty workload"
    )


@pytest.mark.anyio
async def test_total_files_after_registration(
    upload_workload: UploadWorkload,
) -> None:
    """Test total_files reflects registered files."""
    num_files = 5
    files = [MagicMock(spec=File, size=100) for _ in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    assert upload_workload.total_files == num_files, (
        "Expected total_files to match registered count"
    )


def test_remaining_files_empty_workload(upload_workload: UploadWorkload) -> None:
    """Test remaining_files on empty workload."""
    assert upload_workload.remaining_files == 0, (
        "Expected remaining_files to be 0 for empty workload"
    )


@pytest.mark.anyio
async def test_remaining_files_counts_pending_and_in_progress(
    upload_workload: UploadWorkload,
) -> None:
    """Test remaining_files sums pending and in-progress files."""
    num_files = 5
    files = [MagicMock(spec=File, size=100) for _ in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    for _ in range(2):
        await upload_workload._acquire_next_file()

    assert upload_workload.remaining_files == num_files, (
        "Expected remaining_files to match total registered"
    )


@pytest.mark.anyio
async def test_remaining_files_excludes_completed(
    upload_workload: UploadWorkload,
) -> None:
    """Test remaining_files excludes completed files."""
    total_num_files = 5
    files = [
        _create_mock_file(name=f"file_{i}", size=100) for i in range(total_num_files)
    ]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    completing_files_num = 2
    for _ in range(completing_files_num):
        file_obj = await upload_workload._acquire_next_file()
        if not file_obj:
            pytest.fail("Expected a file to acquire")
        result = Result(value=file_obj)
        await upload_workload._mark_completed_result(result)

    remaining_files = total_num_files - completing_files_num
    assert upload_workload.remaining_files == remaining_files


def test_remaining_bytes_empty_workload(upload_workload: UploadWorkload) -> None:
    """Test _remaining_bytes on empty workload."""
    assert upload_workload._remaining_bytes() == 0, (
        "Expected remaining_bytes to be 0 for empty workload"
    )


@pytest.mark.anyio
async def test_remaining_bytes_calculation(
    upload_workload: UploadWorkload,
) -> None:
    """Test _remaining_bytes correctly calculates incomplete bytes."""
    size_list = [100, 200, 300]
    files = [
        _create_mock_file(name=f"file_{i}", size=size)
        for i, size in enumerate(size_list)
    ]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    first_file = await upload_workload._acquire_next_file()
    if not first_file:
        pytest.fail("Expected a file to acquire")
    result = Result(value=first_file)
    await upload_workload._mark_completed_result(result)

    assert upload_workload._remaining_bytes() == sum(size_list[1:]), (
        "Expected remaining_bytes to exclude completed file size"
    )


@pytest.mark.anyio
async def test_remaining_bytes_all_completed(
    upload_workload: UploadWorkload,
) -> None:
    """Test _remaining_bytes returns 0 when all files completed."""
    num_files = 3
    files = [_create_mock_file(name=f"file_{i}", size=100) for i in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    for _ in range(num_files):
        file_obj = await upload_workload._acquire_next_file()
        if not file_obj:
            pytest.fail("Expected a file to acquire")
        result = Result(value=file_obj)
        await upload_workload._mark_completed_result(result)

    assert upload_workload._remaining_bytes() == 0, (
        "Expected remaining_bytes to be 0 when all completed"
    )


@pytest.mark.anyio
async def test_concurrent_file_acquisition_no_duplicates(
    upload_workload: UploadWorkload,
) -> None:
    """Test concurrent _acquire_next_file calls don't return same file."""
    num_files = 10
    files = [MagicMock(spec=File, size=100) for _ in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    acquired_files: list[File] = []

    async def acquire_worker() -> None:
        while True:
            file_obj = await upload_workload._acquire_next_file()
            if file_obj is None:
                break
            acquired_files.append(file_obj)

    workers = [acquire_worker() for _ in range(3)]
    await asyncio.gather(*workers)

    assert len(acquired_files) == num_files, "Expected all files to be acquired"
    assert len({id(f) for f in acquired_files}) == num_files, (
        "Expected no duplicate acquisitions"
    )


@pytest.mark.anyio
async def test_concurrent_mark_operations(
    upload_workload: UploadWorkload,
) -> None:
    """Test concurrent mark_completed and mark_failed maintain correct state."""
    num_files_even = 10
    files = [
        _create_mock_file(name=f"file_{i}", size=100) for i in range(num_files_even)
    ]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    async def worker(file_obj: File, *, should_fail: bool) -> None:
        if should_fail:
            await upload_workload._mark_failed_file(file_obj, reason="test")
        else:
            result = Result(value=file_obj)
            await upload_workload._mark_completed_result(successful_result=result)

    tasks = []
    for idx, file_obj in enumerate(files):
        should_fail = idx % 2 == 0
        tasks.append(worker(file_obj, should_fail=should_fail))

    await asyncio.gather(*tasks)

    assert len(upload_workload.fq_completed) == num_files_even // 2, (
        "Expected half of files in completed"
    )
    assert len(upload_workload.fq_failed) == num_files_even // 2, (
        "Expected half of files in failed"
    )


@pytest.mark.anyio
async def test_has_pending_files_respects_state_changes(
    upload_workload: UploadWorkload,
) -> None:
    """Test _has_pending_files correctly reflects state changes."""
    files = [MagicMock(spec=File, size=100) for _ in range(3)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    assert await upload_workload._has_pending_files(), (
        "Expected pending files after registration"
    )

    await upload_workload._acquire_next_file()
    assert await upload_workload._has_pending_files(), (
        "Expected pending files after acquiring one"
    )

    await upload_workload._acquire_next_file()
    assert await upload_workload._has_pending_files(), (
        "Expected pending files after acquiring two"
    )

    await upload_workload._acquire_next_file()
    assert not await upload_workload._has_pending_files(), (
        "Expected no pending files after acquiring all"
    )


def test_discover_files_raises_on_nonexistent_root(
    client: Mock,
) -> None:
    """Test _discover_files raises FileNotFoundError for nonexistent root."""
    workload = UploadWorkload(
        client=client,
        local_root=Path("/nonexistent/path"),
    )

    with pytest.raises(FileNotFoundError):
        asyncio.run(workload._discover_files())


def test_discover_files_raises_on_file_root(tmp_path: Path, client: Client) -> None:
    """Test _discover_files raises NotADirectoryError when root is a file."""
    file_path = tmp_path / "file.txt"
    file_path.write_text("test", encoding="utf-8")

    workload = UploadWorkload(
        client=client,
        local_root=file_path,
    )

    with pytest.raises(NotADirectoryError):
        asyncio.run(workload._discover_files())


@pytest.mark.anyio
async def test_discover_files_sets_timestamps(tmp_path: Path, client: Client) -> None:
    """Test _discover_files sets discovery_started_at and discovery_finished_at."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "file.txt").write_text("test", encoding="utf-8")

    workload = UploadWorkload(client=client, local_root=root)
    before = datetime.now(UTC)

    with patch.object(file_ops, "is_valid_file", return_value=(True, [])):
        await workload._discover_files()

    after = datetime.now(UTC)

    assert workload.discovery_started_at is not None
    assert workload.discovery_finished_at is not None
    assert (
        before - timedelta(seconds=1)
        <= workload.discovery_started_at
        <= after + timedelta(seconds=1)
    ), "discovery_started_at out of expected range"
    assert (
        before - timedelta(seconds=1)
        <= workload.discovery_finished_at
        <= after + timedelta(seconds=1)
    ), "discovery_finished_at out of expected range"


@pytest.mark.anyio
async def test_discover_files_skips_directories(tmp_path: Path, client: Client) -> None:
    """Test _discover_files doesn't treat directories as files."""
    root = tmp_path / "root"
    root.mkdir()
    subdir = root / "subdir"
    subdir.mkdir()

    workload = UploadWorkload(client=client, local_root=root)

    with patch.object(file_ops, "is_valid_file") as mock_is_valid:
        await workload._discover_files()

    mock_is_valid.assert_not_called()


@pytest.mark.anyio
async def test_discover_files_populates_buffers(tmp_path: Path, client: Client) -> None:
    """Test _discover_files populates discovered and pending buffers."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "file1.txt").write_text("test1", encoding="utf-8")
    (root / "file2.txt").write_text("test2", encoding="utf-8")
    file_count = len(list(root.iterdir()))

    workload = UploadWorkload(client=client, local_root=root)

    with patch.object(file_ops, "is_valid_file", return_value=(True, [])):
        discovered = await workload._discover_files()

    assert len(discovered) == file_count, (
        "Expected discovered files to match file count"
    )
    assert len(workload.fq_discovered) == file_count, (
        "Expected fq_discovered to match file count"
    )
    assert len(workload.fq_pending) == file_count, (
        "Expected fq_pending to match file count"
    )


@pytest.mark.anyio
async def test_discover_files_handles_invalid_files(
    tmp_path: Path, client: Client
) -> None:
    """Test _discover_files handles invalid files correctly."""
    root = tmp_path / "root"
    root.mkdir()
    (root / "valid.txt").write_text("test", encoding="utf-8")
    (root / "invalid.bin").write_bytes(b"\x00\x01\x02")

    workload = UploadWorkload(client=client, local_root=root)

    def is_valid_side_effect(file_path: Path, **kwargs: bool) -> tuple[bool, list[str]]:
        return (
            file_path.suffix == ".txt",
            ["binary file"] if file_path.suffix != ".txt" else [],
        )

    with patch.object(file_ops, "is_valid_file", side_effect=is_valid_side_effect):
        discovered = await workload._discover_files()

    assert len(discovered) == 1
    assert len(workload.fq_skipped) == 1


@pytest.mark.anyio
async def test_periodic_progress_logger_emits_logs(
    upload_workload: UploadWorkload, client: Client
) -> None:
    """Test that the periodic progress logger emits logs every N seconds."""
    # Set a very short period to avoid waiting
    upload_workload.progress_log_period_secs = 0.01

    with patch("spectrumx.api.uploads.log") as mock_log:
        # log.bind(...) returns a logger instance, so we mock that return value
        mock_log.bind.return_value = mock_log

        # Start the logger in a task
        task = asyncio.create_task(upload_workload._periodic_progress_logger())

        # Wait for a few log intervals
        await asyncio.sleep(0.05)

        # Cancel and cleanup
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

        # Verify that the logger's info method was called
        assert mock_log.info.called, "Expected progress logger to emit at least one log"

        # Verify the log content contains "Upload progress"
        first_call_args = mock_log.info.call_args[0]
        assert "Upload progress" in first_call_args[0]


def test_remove_from_buffer_handles_missing_file(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _remove_from_buffer doesn't raise when file isn't in buffer."""
    UploadWorkload._remove_from_buffer(mock_file, upload_workload.fq_pending)


def test_remove_from_buffer_removes_file(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _remove_from_buffer successfully removes file."""
    upload_workload.fq_pending.append(mock_file)

    UploadWorkload._remove_from_buffer(mock_file, upload_workload.fq_pending)

    assert mock_file not in upload_workload.fq_pending


@pytest.mark.anyio
async def test_upload_next_file_credits_unstreamed_bytes(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Upload progress should reach file size when content is not fully streamed."""
    mock_file.size = 1000
    await upload_workload._register_discovered_file(mock_file)
    prog_bar = MagicMock()
    upload_workload._prog_uploaded_bytes = prog_bar

    def fake_upload_file(*, progress_callback=None, **kwargs):
        if progress_callback is not None:
            progress_callback(250)
        return mock_file

    with patch.object(
        upload_workload.client._sds_files,
        "upload_file",
        side_effect=fake_upload_file,
    ):
        result = await upload_workload._upload_next_file()

    assert result
    prog_bar.update.assert_any_call(250)
    prog_bar.update.assert_any_call(750)


@pytest.mark.anyio
async def test_upload_next_file_credits_metadata_only_upload(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Upload progress should reach file size for metadata-only uploads."""
    mock_file.size = 1000
    await upload_workload._register_discovered_file(mock_file)
    prog_bar = MagicMock()
    upload_workload._prog_uploaded_bytes = prog_bar

    with patch.object(
        upload_workload.client._sds_files,
        "upload_file",
        return_value=mock_file,
    ):
        result = await upload_workload._upload_next_file()

    assert result
    prog_bar.update.assert_called_once_with(1000)


@pytest.mark.anyio
async def test_concurrent_upload_progress_bar_byte_count(
    tmp_path: Path, client: Client
) -> None:
    """Concurrent upload workers must not lose byte-count updates on the shared bar."""
    root = tmp_path / "upload_root"
    root.mkdir()

    num_files = 4
    chunk_size = 50_000
    chunks_per_file = 4
    file_size = chunk_size * chunks_per_file
    files = [
        _create_mock_file(name=f"file_{i}.bin", size=file_size)
        for i in range(num_files)
    ]

    workload = UploadWorkload(
        client=client,
        local_root=root,
        sds_path=PurePosixPath("/"),
        max_concurrent_uploads=num_files,
        verbose=True,
    )
    for file_obj in files:
        await workload._register_discovered_file(file_obj)

    def mock_upload_file(
        *,
        client: Client,
        local_file: File,
        sds_path: PurePosixPath,
        progress_callback: Callable[[int], None] | None = None,
    ) -> File:
        del client, sds_path
        if progress_callback is not None:
            for _ in range(chunks_per_file):
                progress_callback(chunk_size)
        return local_file

    with patch.object(
        workload.client._sds_files,
        "upload_file",
        side_effect=mock_upload_file,
    ):
        await workload._execute_uploads()

        expected_bytes = file_size * num_files
        assert isinstance(workload._prog_uploaded_bytes, tqdm)
        assert workload._prog_uploaded_bytes.n == expected_bytes, (
            "Expected progress bar byte count to match total uploaded bytes"
        )
