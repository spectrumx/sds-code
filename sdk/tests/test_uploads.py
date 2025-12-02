"""Tests for the uploads API utilities."""

from __future__ import annotations

import asyncio
import json
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
from spectrumx.api.uploads import MAX_DAYS_FOR_RESUMING_UPLOAD
from spectrumx.api.uploads import PersistedUploadFile
from spectrumx.api.uploads import SkippedUpload
from spectrumx.api.uploads import UploadPersistenceManager
from spectrumx.api.uploads import UploadWorkload
from spectrumx.api.uploads import create_file_instance
from spectrumx.errors import Result
from spectrumx.errors import UploadError
from spectrumx.models.files.file import File
from spectrumx.ops import files as file_ops

if TYPE_CHECKING:
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
) -> File:
    """Helper to create a mock File with required attributes."""
    file_mock = MagicMock(spec=File)
    file_mock.name = name
    file_mock.size = size
    file_mock.directory = PurePosixPath("test_dir")
    file_mock.local_path = local_path or Path(name)
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


@pytest.fixture
def persistence_manager(tmp_path: Path, client: Client) -> UploadPersistenceManager:
    """Create an UploadPersistenceManager instance for testing."""
    root = tmp_path / "upload_root"
    root.mkdir()
    return UploadPersistenceManager(
        local_root=root,
        client=client,
        persist_state=True,
    )


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

    assert workload.local_root == root
    assert workload.sds_path == PurePosixPath("/")
    assert workload.max_concurrent_uploads == default_max_concurrent_uploads
    assert workload.total_files == 0
    assert workload.total_bytes == 0


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

    assert workload.sds_path == PurePosixPath("/custom/path")
    assert workload.max_concurrent_uploads == max_concurrent_uploads


def test_upload_workload_alias_population(tmp_path: Path, client: Client) -> None:
    """Test UploadWorkload respects local_path alias."""
    root = tmp_path / "root"
    root.mkdir()

    workload = UploadWorkload(
        client=client,
        local_root=root,
    )

    assert workload.local_root == root


@pytest.mark.anyio
async def test_register_discovered_file_updates_all_state(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _register_discovered_file updates discovered, pending, and total_bytes."""
    initial_bytes = upload_workload.total_bytes

    await upload_workload._register_discovered_file(mock_file)

    assert mock_file in upload_workload.fq_discovered
    assert mock_file in upload_workload.fq_pending
    assert upload_workload.total_bytes == initial_bytes + mock_file.size
    assert upload_workload.total_files == 1


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

    assert upload_workload.total_bytes == file_size_bytes * total_num_files
    assert upload_workload.total_files == total_num_files


@pytest.mark.anyio
async def test_add_skipped_records_skipped_files(
    upload_workload: UploadWorkload,
) -> None:
    """Test that _add_skipped correctly stores skipped files."""
    path = Path("/tmp/test.txt")  # noqa: S108
    reasons = ("reason1", "reason2")
    skipped = SkippedUpload(path=path, reasons=reasons)

    await upload_workload._add_skipped(skipped)

    assert len(upload_workload.fq_skipped) == 1
    assert upload_workload.fq_skipped[0].path == path
    assert upload_workload.fq_skipped[0].reasons == reasons


@pytest.mark.anyio
async def test_acquire_next_file_moves_to_in_progress(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _acquire_next_file moves file from pending to in-progress."""
    await upload_workload._register_discovered_file(mock_file)

    acquired = await upload_workload._acquire_next_file()

    assert acquired == mock_file
    assert mock_file not in upload_workload.fq_pending
    assert mock_file in upload_workload.fq_in_progress


@pytest.mark.anyio
async def test_acquire_next_file_returns_none_when_empty(
    upload_workload: UploadWorkload,
) -> None:
    """Test _acquire_next_file returns None when no pending files."""
    result = await upload_workload._acquire_next_file()

    assert result is None


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
        assert acquired == expected_file


@pytest.mark.anyio
async def test_mark_completed_transitions_file_state(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_completed removes from in_progress and adds to completed."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    result = Result(value=mock_file)
    await upload_workload._mark_completed_result(successful_result=result)

    assert mock_file not in upload_workload.fq_in_progress
    assert mock_file in upload_workload.fq_completed


@pytest.mark.anyio
async def test_mark_completed_prevents_duplicates(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_completed prevents adding the same file twice."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    result = Result(value=mock_file)
    await upload_workload._mark_completed_result(successful_result=result)

    assert upload_workload.fq_completed.count(mock_file) == 1


@pytest.mark.anyio
async def test_mark_failed_transitions_file_state(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_failed removes from in_progress and adds to failed."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    await upload_workload._mark_failed_file(mock_file, reason="test error")

    assert mock_file not in upload_workload.fq_in_progress
    assert len(upload_workload.fq_failed) == 1
    assert upload_workload.fq_failed[0].sds_file == mock_file
    assert upload_workload.fq_failed[0].reason == "test error"


@pytest.mark.anyio
async def test_mark_failed_with_none_reason(
    upload_workload: UploadWorkload, mock_file: File
) -> None:
    """Test _mark_failed handles None reason gracefully."""
    await upload_workload._register_discovered_file(mock_file)
    await upload_workload._acquire_next_file()

    await upload_workload._mark_failed_file(mock_file, reason=None)

    assert len(upload_workload.fq_failed) == 1
    assert upload_workload.fq_failed[0].reason is None


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
    assert isinstance(error, UploadError)
    assert error.sds_file == mock_file
    assert error.reason == reason_text


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

    assert upload_workload.fq_discovered == files
    assert len(upload_workload.fq_pending) == num_files


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

    assert set(upload_workload.fq_pending) == set(files)


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

    assert len(upload_workload.fq_in_progress) == 0
    assert len(upload_workload.fq_completed) == 0
    assert len(upload_workload.fq_failed) == 0


@pytest.mark.anyio
async def test_reset_state_clears_all_buffers(
    upload_workload: UploadWorkload,
) -> None:
    """Test _reset_state completely empties all file queues."""
    files = [MagicMock(spec=File, size=100) for _ in range(3)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    await upload_workload._reset_state()

    assert len(upload_workload.fq_discovered) == 0
    assert len(upload_workload.fq_pending) == 0
    assert len(upload_workload.fq_in_progress) == 0
    assert len(upload_workload.fq_completed) == 0
    assert len(upload_workload.fq_failed) == 0
    assert len(upload_workload.fq_skipped) == 0


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

    assert upload_workload.total_bytes == 0


def test_total_files_property(upload_workload: UploadWorkload) -> None:
    """Test total_files returns correct count of discovered files."""
    assert upload_workload.total_files == 0


@pytest.mark.anyio
async def test_total_files_after_registration(
    upload_workload: UploadWorkload,
) -> None:
    """Test total_files reflects registered files."""
    num_files = 5
    files = [MagicMock(spec=File, size=100) for _ in range(num_files)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    assert upload_workload.total_files == num_files


def test_remaining_files_empty_workload(upload_workload: UploadWorkload) -> None:
    """Test remaining_files on empty workload."""
    assert upload_workload.remaining_files == 0


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

    assert upload_workload.remaining_files == num_files


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
    assert upload_workload._remaining_bytes() == 0


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

    assert upload_workload._remaining_bytes() == sum(size_list[1:])


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

    assert upload_workload._remaining_bytes() == 0


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

    assert len(acquired_files) == num_files
    assert len({id(f) for f in acquired_files}) == num_files


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

    assert len(upload_workload.fq_completed) == num_files_even // 2
    assert len(upload_workload.fq_failed) == num_files_even // 2


@pytest.mark.anyio
async def test_has_pending_files_respects_state_changes(
    upload_workload: UploadWorkload,
) -> None:
    """Test _has_pending_files correctly reflects state changes."""
    files = [MagicMock(spec=File, size=100) for _ in range(3)]
    for file_obj in files:
        await upload_workload._register_discovered_file(file_obj)

    assert await upload_workload._has_pending_files()

    await upload_workload._acquire_next_file()
    assert await upload_workload._has_pending_files()

    await upload_workload._acquire_next_file()
    assert await upload_workload._has_pending_files()

    await upload_workload._acquire_next_file()
    assert not await upload_workload._has_pending_files()


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
    assert before <= workload.discovery_started_at <= after
    assert before <= workload.discovery_finished_at <= after


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

    assert len(discovered) == file_count
    assert len(workload.fq_discovered) == file_count
    assert len(workload.fq_pending) == file_count


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
    assert workload.fq_skipped[0].path == root / "invalid.bin"


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
async def test_load_persisted_uploads_empty_when_disabled(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test load_persisted_uploads returns empty dict when persist_state=False."""
    persistence_manager.persist_state = False

    result = await persistence_manager.load_persisted_uploads()

    assert result == {}


@pytest.mark.anyio
async def test_load_persisted_uploads_no_file(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test load_persisted_uploads returns empty dict when no persisted file."""
    persistence_manager.persist_state = True

    result = await persistence_manager.load_persisted_uploads()

    assert result == {}


@pytest.mark.anyio
async def test_get_persisted_uploads_dir_creates_directory(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test _get_persisted_uploads_dir creates the directory if it doesn't exist."""
    uploads_dir = persistence_manager._get_persisted_uploads_dir()

    assert uploads_dir.exists()
    assert uploads_dir.is_dir()


@pytest.mark.anyio
async def test_get_persisted_uploads_path_consistent(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test _get_persisted_uploads_path returns consistent path."""
    path1 = persistence_manager._get_persisted_uploads_path()
    path2 = persistence_manager._get_persisted_uploads_path()

    assert path1 == path2


@pytest.mark.anyio
async def test_save_persisted_upload_skipped_when_disabled(
    persistence_manager: UploadPersistenceManager, mock_file: File
) -> None:
    """Test save_persisted_upload does nothing when persist_state=False."""
    persistence_manager.persist_state = False
    mock_file.local_path = Path("/tmp/test.txt")  # noqa: S108

    mock_file.compute_sum_blake3 = MagicMock(return_value="abc123")

    persist_path = persistence_manager._get_persisted_uploads_path()
    initial_exists = persist_path.exists()

    await persistence_manager.save_persisted_upload(mock_file)
    assert persist_path.exists() == initial_exists


@pytest.mark.anyio
async def test_save_persisted_upload_creates_file(
    persistence_manager: UploadPersistenceManager, tmp_path: Path
) -> None:
    """Test save_persisted_upload writes file to persistence."""
    persistence_manager.persist_state = True

    file_path = tmp_path / "test_file.txt"
    file_path.write_text("test content", encoding="utf-8")

    file_model = MagicMock(spec=File)
    file_model.local_path = file_path
    file_model.compute_sum_blake3 = MagicMock(return_value="test_checksum_123")

    persist_path = persistence_manager._get_persisted_uploads_path()

    await persistence_manager.save_persisted_upload(file_model)

    assert persist_path.exists()
    content = persist_path.read_text(encoding="utf-8").strip()
    assert "test_checksum_123" in content
    assert str(file_path.resolve()) in content


@pytest.mark.anyio
async def test_save_persisted_upload_appends_to_file(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _save_persisted_upload appends to existing persistence file."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    file1_path = tmp_path / "file1.txt"
    file1_path.write_text("content1", encoding="utf-8")
    file2_path = tmp_path / "file2.txt"
    file2_path.write_text("content2", encoding="utf-8")

    file1_model = MagicMock(spec=File)
    file1_model.local_path = file1_path
    file1_model.compute_sum_blake3 = MagicMock(return_value="checksum_1")

    file2_model = MagicMock(spec=File)
    file2_model.local_path = file2_path
    file2_model.compute_sum_blake3 = MagicMock(return_value="checksum_2")

    await upload_workload._persistence_manager.save_persisted_upload(file1_model)
    await upload_workload._persistence_manager.save_persisted_upload(file2_model)

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    expected_persisted_files = 2
    assert len(lines) == expected_persisted_files
    assert "checksum_1" in lines[0]
    assert "checksum_2" in lines[1]


@pytest.mark.anyio
async def test_discover_files_skips_already_uploaded(
    tmp_path: Path, client: Client
) -> None:
    """Test _discover_files skips files that have already been uploaded."""
    root = tmp_path / "upload_root"
    root.mkdir()

    file1 = root / "file1.txt"
    file1.write_text("content1", encoding="utf-8")
    file2 = root / "file2.txt"
    file2.write_text("content2", encoding="utf-8")

    workload = UploadWorkload(
        client=client,
        local_root=root,
        persist_state=True,
    )

    assert workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = workload._persistence_manager._get_persisted_uploads_path()
    file1_checksum = str(file1.stat().st_size)  # use size as fake checksum
    persisted = PersistedUploadFile(
        resolved_path=file1.resolve(),
        sum_blake3=file1_checksum,
    )

    with persist_path.open("w", encoding="utf-8") as f:
        f.write(persisted.model_dump_json() + "\n")

    def mock_compute_sum_blake3(self: object) -> str | None:
        if hasattr(self, "local_path"):
            self_local_path = self.local_path
            if self_local_path.resolve() == file1.resolve():
                return file1_checksum
        return "different_checksum"

    with patch.object(File, "compute_sum_blake3", mock_compute_sum_blake3):
        discovered = await workload._discover_files()

        assert len(discovered) == 1
        assert discovered[0].name == "file2.txt"


@pytest.mark.anyio
async def test_mark_completed_persists_file(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _mark_completed saves the file to persistence."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    file_path = tmp_path / "uploaded_file.txt"
    file_path.write_text("uploaded content", encoding="utf-8")

    file_model = MagicMock(spec=File)
    file_model.local_path = file_path
    file_model.size = 100
    file_model.compute_sum_blake3 = MagicMock(return_value="persisted_checksum")
    await upload_workload._register_discovered_file(file_model=file_model)
    await upload_workload._acquire_next_file()

    result: Result[File] = Result(value=file_model)
    await upload_workload._mark_completed_result(successful_result=result)

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    assert persist_path.exists()
    content = persist_path.read_text(encoding="utf-8")
    assert "persisted_checksum" in content
    assert str(file_path.resolve()) in content


@pytest.mark.anyio
async def test_persisted_uploads_path_deterministic(
    tmp_path: Path, client: Client
) -> None:
    """Test that the same local_root produces the same persisted path."""
    root = tmp_path / "upload_root"
    root.mkdir()

    workload1 = UploadWorkload(client=client, local_root=root)
    workload2 = UploadWorkload(client=client, local_root=root)

    assert workload1._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    assert workload2._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    path1 = workload1._persistence_manager._get_persisted_uploads_path()
    path2 = workload2._persistence_manager._get_persisted_uploads_path()

    assert path1 == path2


@pytest.mark.anyio
async def test_persisted_uploads_path_different_for_different_roots(
    tmp_path: Path, client: Client
) -> None:
    """Test that different local_roots produce different persisted paths."""
    root1 = tmp_path / "upload_root1"
    root1.mkdir()
    root2 = tmp_path / "upload_root2"
    root2.mkdir()

    workload1 = UploadWorkload(client=client, local_root=root1)
    workload2 = UploadWorkload(client=client, local_root=root2)

    assert workload1._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    assert workload2._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    path1 = workload1._persistence_manager._get_persisted_uploads_path()
    path2 = workload2._persistence_manager._get_persisted_uploads_path()

    assert path1 != path2


@pytest.mark.anyio
async def test_load_persisted_uploads_handles_corrupt_json(
    upload_workload: UploadWorkload,
) -> None:
    """Test graceful handling of corrupted JSONL entries."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()

    persist_path.write_text("invalid json\n")

    result = await upload_workload._persistence_manager.load_persisted_uploads()

    assert result == {}


@pytest.mark.anyio
async def test_save_persisted_upload_handles_write_error(
    upload_workload: UploadWorkload, mock_file: File, tmp_path: Path
) -> None:
    """Test graceful handling when persistence write fails."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    uploads_dir = UploadPersistenceManager._get_persisted_uploads_dir()
    original_mode = uploads_dir.stat().st_mode
    try:
        uploads_dir.chmod(0o444)

        await upload_workload._persistence_manager.save_persisted_upload(mock_file)
    finally:
        uploads_dir.chmod(original_mode)


@pytest.mark.anyio
async def test_discover_files_detects_updated_file_via_checksum(
    tmp_path: Path, client: Client
) -> None:
    """Test that file with changed content is NOT skipped (checksum differs)."""
    root = tmp_path / "upload_root"
    root.mkdir()
    file1 = root / "file.txt"
    file1.write_text("original", encoding="utf-8")

    workload = UploadWorkload(client=client, local_root=root, persist_state=True)

    assert workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = workload._persistence_manager._get_persisted_uploads_path()
    old_checksum = "old_checksum_abc"
    persisted = PersistedUploadFile(
        resolved_path=file1.resolve(),
        sum_blake3=old_checksum,
    )
    persist_path.write_text(persisted.model_dump_json() + "\n")

    file1.write_text("modified", encoding="utf-8")

    with patch.object(File, "compute_sum_blake3") as mock_checksum:
        mock_checksum.return_value = "new_checksum_def"
        discovered = await workload._discover_files()

    assert len(discovered) == 1
    assert discovered[0].name == "file.txt"


@pytest.mark.anyio
async def test_persistence_full_workflow(tmp_path: Path, client: Client) -> None:
    """Test persistence across multiple discovery and upload cycles."""
    root = tmp_path / "upload_root"
    root.mkdir()
    file1 = root / "file1.txt"
    file1.write_text("content1", encoding="utf-8")

    workload = UploadWorkload(client=client, local_root=root, persist_state=True)

    assert workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    discovered1 = await workload._discover_files()
    assert len(discovered1) == 1
    assert len(workload.fq_pending) == 1

    file_obj = discovered1[0]
    await workload._mark_completed_result(successful_result=Result(value=file_obj))

    persist_path = workload._persistence_manager._get_persisted_uploads_path()
    assert persist_path.exists()
    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1

    workload2 = UploadWorkload(client=client, local_root=root, persist_state=True)
    discovered2 = await workload2._discover_files()

    assert len(discovered2) == 0
    assert len(workload2.fq_pending) == 0


@pytest.mark.anyio
async def test_remove_persisted_upload_disabled_when_persist_state_false(
    upload_workload: UploadWorkload,
) -> None:
    """Test _remove_persisted_upload does nothing when persist_state=False."""
    upload_workload.persist_state = False
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()

    await upload_workload._persistence_manager.remove_persisted_upload("/some/path")
    assert not persist_path.exists()


@pytest.mark.anyio
async def test_remove_persisted_upload_no_file_exists(
    upload_workload: UploadWorkload,
) -> None:
    """Test _remove_persisted_upload returns early if persistence file doesn't exist."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()

    assert not persist_path.exists()
    await upload_workload._persistence_manager.remove_persisted_upload("/some/path")
    assert not persist_path.exists()


@pytest.mark.anyio
async def test_remove_persisted_upload_removes_single_entry(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _remove_persisted_upload removes a single entry from persistence."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    file_path = tmp_path / "test_file.txt"
    file_path.write_text("content", encoding="utf-8")
    resolved_path = str(file_path.resolve())

    persisted = PersistedUploadFile(
        resolved_path=file_path.resolve(),
        sum_blake3="checksum_123",
    )

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    persist_path.write_text(persisted.model_dump_json() + "\n")

    await upload_workload._persistence_manager.remove_persisted_upload(resolved_path)
    content = persist_path.read_text(encoding="utf-8").strip()
    assert content == ""


@pytest.mark.anyio
async def test_remove_persisted_upload_removes_from_multiple_entries(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _remove_persisted_upload removes specific entry from multiple entries."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    file_paths = [
        tmp_path / "file1.txt",
        tmp_path / "file2.txt",
        tmp_path / "file3.txt",
    ]
    for file_path in file_paths:
        file_path.write_text("content", encoding="utf-8")

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    for idx, file_path in enumerate(file_paths):
        persisted = PersistedUploadFile(
            resolved_path=file_path.resolve(),
            sum_blake3=f"checksum_{idx}",
        )
        with persist_path.open("a", encoding="utf-8") as f:
            f.write(persisted.model_dump_json() + "\n")

    await upload_workload._persistence_manager.remove_persisted_upload(
        str(file_paths[1].resolve())
    )

    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    expected_remaining_entries = 2
    assert len(lines) == expected_remaining_entries
    first_entry_idx = 0
    second_entry_idx = 1
    assert "checksum_0" in lines[first_entry_idx]
    assert "checksum_2" in lines[second_entry_idx]
    assert "checksum_1" not in persist_path.read_text(encoding="utf-8")


@pytest.mark.anyio
async def test_remove_persisted_upload_nonexistent_entry(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _remove_persisted_upload handles removal of nonexistent entry gracefully."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    file_path = tmp_path / "file1.txt"
    file_path.write_text("content", encoding="utf-8")

    persisted = PersistedUploadFile(
        resolved_path=file_path.resolve(),
        sum_blake3="checksum_1",
    )

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    persist_path.write_text(persisted.model_dump_json() + "\n")

    nonexistent = tmp_path / "nonexistent.txt"
    await upload_workload._persistence_manager.remove_persisted_upload(
        str(nonexistent.resolve())
    )

    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1
    assert "checksum_1" in lines[0]


@pytest.mark.anyio
async def test_rewrite_persisted_uploads_excluding_empty_file(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _rewrite_persisted_uploads_excluding on empty persistence file."""
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = tmp_path / "empty_uploads.jsonl"
    persist_path.write_text("")

    await upload_workload._persistence_manager._rewrite_persisted_uploads_excluding(
        persist_path,
        {"/some/path"},
    )

    assert persist_path.read_text(encoding="utf-8") == ""


@pytest.mark.anyio
async def test_rewrite_persisted_uploads_excluding_all_entries(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _rewrite_persisted_uploads_excluding can remove all entries."""
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    file_paths = [
        tmp_path / "file1.txt",
        tmp_path / "file2.txt",
    ]
    persist_path = tmp_path / "uploads.jsonl"

    excluded_paths = set()
    for file_path in file_paths:
        file_path.write_text("content", encoding="utf-8")
        persisted = PersistedUploadFile(
            resolved_path=file_path.resolve(),
            sum_blake3="checksum",
        )
        with persist_path.open("a", encoding="utf-8") as f:
            f.write(persisted.model_dump_json() + "\n")
        excluded_paths.add(str(file_path.resolve()))

    await upload_workload._persistence_manager._rewrite_persisted_uploads_excluding(
        persist_path,
        excluded_paths,
    )

    content = persist_path.read_text(encoding="utf-8").strip()
    assert content == ""


@pytest.mark.anyio
async def test_rewrite_persisted_uploads_excluding_keeps_nonexcluded(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _rewrite_persisted_uploads_excluding preserves non-excluded entries."""
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    file_paths = [
        tmp_path / "file1.txt",
        tmp_path / "file2.txt",
        tmp_path / "file3.txt",
    ]
    persist_path = tmp_path / "uploads.jsonl"

    for idx, file_path in enumerate(file_paths):
        file_path.write_text("content", encoding="utf-8")
        persisted = PersistedUploadFile(
            resolved_path=file_path.resolve(),
            sum_blake3=f"checksum_{idx}",
        )
        with persist_path.open("a", encoding="utf-8") as f:
            f.write(persisted.model_dump_json() + "\n")

    excluded = {str(file_paths[1].resolve())}
    await upload_workload._persistence_manager._rewrite_persisted_uploads_excluding(
        persist_path,
        excluded,
    )

    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    expected_remaining_entries = 2
    assert len(lines) == expected_remaining_entries
    checksums = []
    for line in lines:
        data = json.loads(line)
        checksums.append(data["sum_blake3"])
    assert "checksum_0" in checksums
    assert "checksum_2" in checksums
    assert "checksum_1" not in checksums


@pytest.mark.anyio
async def test_rewrite_persisted_uploads_excluding_handles_corrupt_entries(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _rewrite_persisted_uploads_excluding logs warning on corrupt JSON."""
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = tmp_path / "corrupt_uploads.jsonl"
    persist_path.write_text("invalid json line\n")

    with patch("spectrumx.api.uploads.log_user_warning") as mock_warn:
        await upload_workload._persistence_manager._rewrite_persisted_uploads_excluding(
            persist_path,
            set(),
        )
        mock_warn.assert_called()


@pytest.mark.anyio
async def test_discover_files_removes_stale_entry_on_checksum_mismatch(
    tmp_path: Path, client: Client
) -> None:
    """Test _process_file_candidate removes persisted entry on checksum mismatch."""
    root = tmp_path / "upload_root"
    root.mkdir()
    file_path = root / "file.txt"
    file_path.write_text("original", encoding="utf-8")

    workload = UploadWorkload(client=client, local_root=root, persist_state=True)

    assert workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = workload._persistence_manager._get_persisted_uploads_path()
    old_checksum = "old_checksum_value"
    persisted = PersistedUploadFile(
        resolved_path=file_path.resolve(),
        sum_blake3=old_checksum,
    )
    persist_path.write_text(persisted.model_dump_json() + "\n")

    file_path.write_text("modified", encoding="utf-8")

    with patch.object(File, "compute_sum_blake3") as mock_checksum:
        mock_checksum.return_value = "new_checksum_value"
        discovered = await workload._discover_files()

    assert len(discovered) == 1
    content = persist_path.read_text(encoding="utf-8").strip()
    assert content == ""


@pytest.mark.anyio
async def test_discover_files_removes_expired_entry(
    tmp_path: Path, client: Client
) -> None:
    """Test _process_file_candidate removes persisted entry when it's too old."""

    root = tmp_path / "upload_root"
    root.mkdir()
    file_path = root / "file.txt"
    file_path.write_text("content", encoding="utf-8")

    workload = UploadWorkload(client=client, local_root=root, persist_state=True)

    assert workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = workload._persistence_manager._get_persisted_uploads_path()
    expired_date = datetime.now(UTC) - timedelta(days=MAX_DAYS_FOR_RESUMING_UPLOAD + 1)
    persisted = PersistedUploadFile(
        resolved_path=file_path.resolve(),
        sum_blake3="matching_checksum",
        uploaded_at=expired_date,
    )
    persist_path.write_text(persisted.model_dump_json() + "\n")

    with patch.object(File, "compute_sum_blake3") as mock_checksum:
        mock_checksum.return_value = "matching_checksum"
        discovered = await workload._discover_files()

    assert len(discovered) == 1
    content = persist_path.read_text(encoding="utf-8").strip()
    assert content == ""


@pytest.mark.anyio
async def test_remove_persisted_upload_handles_parse_error(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _remove_persisted_upload logs warning on parse errors."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()

    persist_path.write_text("invalid json\n")

    with patch("spectrumx.api.uploads.log_user_warning") as mock_warn:
        await upload_workload._persistence_manager.remove_persisted_upload("/some/path")
        mock_warn.assert_called()


@pytest.mark.anyio
async def test_remove_persisted_upload_handles_write_error(
    upload_workload: UploadWorkload, tmp_path: Path
) -> None:
    """Test _remove_persisted_upload handles write permission errors gracefully."""
    upload_workload.persist_state = True
    assert upload_workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )

    file_path = tmp_path / "file.txt"
    file_path.write_text("content", encoding="utf-8")

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    persisted = PersistedUploadFile(
        resolved_path=file_path.resolve(),
        sum_blake3="checksum",
    )
    persist_path.write_text(persisted.model_dump_json() + "\n")

    original_open = Path.open
    error_msg = "Permission denied"

    def mock_open_write(self: Path, *args, **kwargs) -> None:
        if kwargs.get("encoding"):
            raise OSError(error_msg)
        return original_open(self, *args, **kwargs)  # pyright: ignore[reportArgumentType]

    with (
        patch.object(Path, "open", mock_open_write),
        patch("spectrumx.api.uploads.log_user_warning") as mock_warn,
    ):
        await upload_workload._persistence_manager.remove_persisted_upload(
            str(file_path.resolve())
        )
        mock_warn.assert_called()


def test_remove_persisted_uploads_by_checksum_no_uploads_dir() -> None:
    """Test remove_persisted_uploads_by_checksum with nonexistent uploads dir."""
    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        nonexistent_path = Path("/nonexistent/xdg/state/dir")
        mock_state_home.return_value = nonexistent_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="some_checksum"
        )


def test_remove_persisted_uploads_by_checksum_removes_single_checksum(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum removes matching checksum entries."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"

    entries = [
        PersistedUploadFile(
            resolved_path=Path("/file1.txt"), sum_blake3="checksum_to_remove"
        ),
        PersistedUploadFile(
            resolved_path=Path("/file2.txt"), sum_blake3="checksum_to_keep"
        ),
        PersistedUploadFile(
            resolved_path=Path("/file3.txt"), sum_blake3="checksum_to_remove"
        ),
    ]

    with persist_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="checksum_to_remove"
        )

    remaining_lines = persist_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(remaining_lines) == 1
    remaining_data = json.loads(remaining_lines[0])
    assert remaining_data["sum_blake3"] == "checksum_to_keep"


def test_remove_persisted_uploads_by_checksum_removes_all_matching(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum removes all matching checksums."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"

    entries = [
        PersistedUploadFile(
            resolved_path=Path("/file1.txt"), sum_blake3="target_checksum"
        ),
        PersistedUploadFile(
            resolved_path=Path("/file2.txt"), sum_blake3="target_checksum"
        ),
        PersistedUploadFile(
            resolved_path=Path("/file3.txt"), sum_blake3="target_checksum"
        ),
    ]

    with persist_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="target_checksum"
        )
    content = persist_file.read_text(encoding="utf-8").strip()
    assert content == ""


def test_remove_persisted_uploads_by_checksum_multiple_files(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum searches multiple persistence files."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file1 = uploads_dir / "aaaaaaaa_uploads.jsonl"
    persist_file2 = uploads_dir / "bbbbbbbb_uploads.jsonl"
    entries1 = [
        PersistedUploadFile(resolved_path=Path("/file1.txt"), sum_blake3="target"),
        PersistedUploadFile(resolved_path=Path("/file2.txt"), sum_blake3="other"),
    ]
    with persist_file1.open("w", encoding="utf-8") as f:
        for entry in entries1:
            f.write(entry.model_dump_json() + "\n")
    entries2 = [
        PersistedUploadFile(resolved_path=Path("/file3.txt"), sum_blake3="target"),
        PersistedUploadFile(resolved_path=Path("/file4.txt"), sum_blake3="target"),
    ]
    with persist_file2.open("w", encoding="utf-8") as f:
        for entry in entries2:
            f.write(entry.model_dump_json() + "\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(checksum="target")
    file1_lines = persist_file1.read_text(encoding="utf-8").strip().split("\n")
    assert len(file1_lines) == 1
    assert "other" in file1_lines[0]
    file2_content = persist_file2.read_text(encoding="utf-8").strip()
    assert file2_content == ""


def test_remove_persisted_uploads_by_checksum_handles_corrupt_json(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum handles corrupt JSON gracefully."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"
    persist_file.write_text("invalid json\nmore invalid\n")

    with (
        patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home,
        patch("spectrumx.api.uploads.log_user_warning") as mock_warn,
    ):
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="some_checksum"
        )

        mock_warn.assert_called()


def test_remove_persisted_uploads_by_checksum_handles_read_error(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum handles read errors gracefully."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"
    persist_file.write_text("some data\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        original_open = Path.open
        call_count = [0]

        def mock_open_impl(
            self: Path, mode: str = "r", *args: object, **kwargs: object
        ) -> object:
            call_count[0] += 1
            if call_count[0] == 1 and "w" not in mode:
                err_msg = "Permission denied"
                raise OSError(err_msg)
            return original_open(self, mode, *args, **kwargs)  # pyright: ignore[reportArgumentType, reportCallIssue]

        with (
            patch.object(Path, "open", mock_open_impl),
            patch("spectrumx.api.uploads.log_user_warning") as mock_warn,
        ):
            UploadPersistenceManager.remove_persisted_uploads_by_checksum(
                checksum="some_checksum"
            )
            mock_warn.assert_called()


def test_remove_persisted_uploads_by_checksum_handles_write_error(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum handles write errors gracefully."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"

    entry = PersistedUploadFile(resolved_path=Path("/file1.txt"), sum_blake3="checksum")
    persist_file.write_text(entry.model_dump_json() + "\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        original_open = Path.open
        call_count = [0]

        def mock_open_impl(
            self: Path, mode: str = "r", *args: object, **kwargs: object
        ) -> object:
            call_count[0] += 1
            if call_count[0] > 1 and "w" in mode:
                err_msg = "Permission denied"
                raise OSError(err_msg)
            return original_open(self, mode, *args, **kwargs)  # pyright: ignore[reportArgumentType, reportCallIssue]

        with (
            patch.object(Path, "open", mock_open_impl),
            patch("spectrumx.api.uploads.log_user_warning") as mock_warn,
        ):
            UploadPersistenceManager.remove_persisted_uploads_by_checksum(
                checksum="checksum"
            )
            mock_warn.assert_called()


def test_remove_persisted_uploads_by_checksum_preserves_other_files(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum doesn't affect non-matching entries."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"

    entries = [
        PersistedUploadFile(resolved_path=Path("/file1.txt"), sum_blake3="checksum_a"),
        PersistedUploadFile(resolved_path=Path("/file2.txt"), sum_blake3="checksum_b"),
        PersistedUploadFile(resolved_path=Path("/file3.txt"), sum_blake3="checksum_c"),
    ]

    with persist_file.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="checksum_b"
        )

    remaining_lines = persist_file.read_text(encoding="utf-8").strip().split("\n")
    expected_count = 2
    assert len(remaining_lines) == expected_count

    checksums = [json.loads(line)["sum_blake3"] for line in remaining_lines]
    assert "checksum_a" in checksums
    assert "checksum_c" in checksums
    assert "checksum_b" not in checksums


def test_remove_persisted_uploads_by_checksum_empty_persistence_file(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum handles empty persistence files."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"
    persist_file.write_text("")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="some_checksum"
        )
    assert persist_file.read_text(encoding="utf-8") == ""


def test_remove_persisted_uploads_by_checksum_with_empty_lines(
    tmp_path: Path,
) -> None:
    """Test remove_persisted_uploads_by_checksum skips empty lines."""
    uploads_dir = tmp_path / "spectrumx" / "uploads"
    uploads_dir.mkdir(parents=True)

    persist_file = uploads_dir / "abc12345_uploads.jsonl"

    entry = PersistedUploadFile(resolved_path=Path("/file1.txt"), sum_blake3="checksum")
    persist_file.write_text(entry.model_dump_json() + "\n\n\n")

    with patch("spectrumx.api.uploads.xdg_state_home") as mock_state_home:
        mock_state_home.return_value = tmp_path

        UploadPersistenceManager.remove_persisted_uploads_by_checksum(
            checksum="different_checksum"
        )
    lines = [
        line
        for line in persist_file.read_text(encoding="utf-8").split("\n")
        if line.strip()
    ]
    assert len(lines) == 1
    assert "checksum" in lines[0]
