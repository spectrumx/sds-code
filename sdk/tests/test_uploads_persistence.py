"""Tests for the uploads API utilities — UploadPersistenceManager."""

from __future__ import annotations

import json
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from anyio import Path as AnyioPath
from spectrumx.api.uploads import MAX_DAYS_FOR_RESUMING_UPLOAD
from spectrumx.api.uploads import PersistedUploadFile
from spectrumx.api.uploads import UploadPersistenceManager
from spectrumx.api.uploads import UploadWorkload
from spectrumx.errors import Result
from spectrumx.models.files.file import File

if TYPE_CHECKING:
    from spectrumx.client import Client

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false


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


@pytest.mark.anyio
async def test_load_persisted_uploads_empty_when_disabled(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test load_persisted_uploads returns empty dict when persist_state=False."""
    persistence_manager.persist_state = False

    result = await persistence_manager.load_persisted_uploads()

    assert result == {}, "Expected empty dict when persist_state is disabled"


@pytest.mark.anyio
async def test_load_persisted_uploads_no_file(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test load_persisted_uploads returns empty dict when no persisted file."""
    persistence_manager.persist_state = True

    result = await persistence_manager.load_persisted_uploads()

    assert result == {}, "Expected empty dict when no persisted file exists"


@pytest.mark.anyio
async def test_get_persisted_uploads_dir_creates_directory(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test _get_persisted_uploads_dir creates the directory if it doesn't exist."""
    uploads_dir = persistence_manager._get_persisted_uploads_dir()

    assert uploads_dir.exists(), "Expected uploads dir to exist"
    assert uploads_dir.is_dir(), "Expected uploads dir to be a directory"


@pytest.mark.anyio
async def test_get_persisted_uploads_path_consistent(
    persistence_manager: UploadPersistenceManager,
) -> None:
    """Test _get_persisted_uploads_path returns consistent path."""
    path1 = persistence_manager._get_persisted_uploads_path()
    path2 = persistence_manager._get_persisted_uploads_path()

    assert path1 == path2, "Expected consistent persisted uploads path"


@pytest.mark.anyio
async def test_save_persisted_upload_skipped_when_disabled(
    persistence_manager: UploadPersistenceManager, mock_file: File
) -> None:
    """Test save_persisted_upload does nothing when persist_state=False."""
    persistence_manager.persist_state = False
    mock_file.local_path = Path("/tmp/test.txt")  # noqa: S108

    mock_file.compute_sum_blake3.return_value = "abc123"

    persist_path = persistence_manager._get_persisted_uploads_path()
    initial_exists = persist_path.exists()

    await persistence_manager.save_persisted_upload(mock_file)
    assert persist_path.exists() == initial_exists, (
        "Expected persist file existence to be unchanged when disabled"
    )


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
    file_model.compute_sum_blake3.return_value = "test_checksum_123"

    persist_path = persistence_manager._get_persisted_uploads_path()

    await persistence_manager.save_persisted_upload(file_model)

    assert persist_path.exists(), "Expected persist file to be created"
    content = persist_path.read_text(encoding="utf-8").strip()
    assert "test_checksum_123" in content, "Expected checksum in persisted content"
    assert str(file_path.resolve()) in content, (
        "Expected file path in persisted content"
    )


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
    file1_model.compute_sum_blake3.return_value = "checksum_1"

    file2_model = MagicMock(spec=File)
    file2_model.local_path = file2_path
    file2_model.compute_sum_blake3.return_value = "checksum_2"

    await upload_workload._persistence_manager.save_persisted_upload(file1_model)
    await upload_workload._persistence_manager.save_persisted_upload(file2_model)

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    expected_persisted_files = 2
    assert len(lines) == expected_persisted_files, "Expected 2 persisted file entries"
    assert "checksum_1" in lines[0], "Expected checksum_1 in first line"
    assert "checksum_2" in lines[1], "Expected checksum_2 in second line"


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

        assert len(discovered) == 1, (
            "Expected only 1 discovered file (skipping the already uploaded one)"
        )
        assert discovered[0].name == "file2.txt", "Expected file2.txt to be discovered"


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
    file_model.compute_sum_blake3.return_value = "persisted_checksum"
    await upload_workload._register_discovered_file(file_model=file_model)
    await upload_workload._acquire_next_file()

    result: Result[File] = Result(value=file_model)
    await upload_workload._mark_completed_result(successful_result=result)

    persist_path = upload_workload._persistence_manager._get_persisted_uploads_path()
    assert persist_path.exists(), (
        "Expected persist file to exist after completing upload"
    )
    content = persist_path.read_text(encoding="utf-8")
    assert "persisted_checksum" in content, "Expected checksum in persisted content"
    assert str(file_path.resolve()) in content, (
        "Expected file path in persisted content"
    )


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

    assert path1 == path2, "Expected same root to produce same persisted path"


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

    assert path1 != path2, (
        "Expected different roots to produce different persisted paths"
    )


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

    assert result == {}, "Expected empty result for corrupt JSON"


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

    assert len(discovered) == 1, "Expected 1 discovered file despite checksum mismatch"
    assert discovered[0].name == "file.txt", "Expected file.txt to be discovered"


@pytest.mark.anyio
async def test_persistence_full_workflow(tmp_path: Path, client: Client) -> None:
    """Test persistence across multiple discovery and upload cycles."""
    root = AnyioPath(tmp_path) / "upload_root"
    await root.mkdir()
    file1 = root / "file1.txt"
    await file1.write_text("content1", encoding="utf-8")

    file_exists = await file1.exists()
    assert file_exists, "Test setup failed: file1 was not created successfully"

    workload = UploadWorkload(client=client, local_root=Path(root), persist_state=True)

    assert workload._persistence_manager is not None, (
        "Persistence manager should be initialized"
    )
    discovered1 = await workload._discover_files()
    assert len(discovered1) == 1, "Expected to discover one file"
    assert len(workload.fq_pending) == 1, "Expected pending buffer to have one file"

    file_obj = discovered1[0]
    await workload._mark_completed_result(successful_result=Result(value=file_obj))

    persist_path = workload._persistence_manager._get_persisted_uploads_path()
    assert persist_path.exists(), "Expected persist file to exist"
    lines = persist_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 1, "Expected 1 persisted entry"

    workload2 = UploadWorkload(client=client, local_root=Path(root), persist_state=True)
    discovered2 = await workload2._discover_files()

    assert len(discovered2) == 0, "Expected no files to be discovered (all persisted)"
    assert len(workload2.fq_pending) == 0, "Expected no pending files"


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
    assert not persist_path.exists(), "Expected persist file to not exist when disabled"


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

    assert not persist_path.exists(), "Expected persist file to not exist initially"
    await upload_workload._persistence_manager.remove_persisted_upload("/some/path")
    assert not persist_path.exists(), (
        "Expected persist file to still not exist after removal"
    )


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
    assert content == "", "Expected empty content after removing single entry"


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
    assert len(lines) == expected_remaining_entries, (
        "Expected 2 remaining entries after removing middle one"
    )
    first_entry_idx = 0
    second_entry_idx = 1
    assert "checksum_0" in lines[first_entry_idx], "Expected checksum_0 in first entry"
    assert "checksum_2" in lines[second_entry_idx], (
        "Expected checksum_2 in second entry"
    )
    assert "checksum_1" not in persist_path.read_text(encoding="utf-8"), (
        "Expected checksum_1 to be removed"
    )


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
    assert len(lines) == 1, "Expected 1 remaining entry after removing nonexistent"
    assert "checksum_1" in lines[0], "Expected checksum_1 to remain"


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

    assert persist_path.read_text(encoding="utf-8") == "", (
        "Expected empty file after rewrite on empty file"
    )


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
    assert content == "", "Expected empty file after removing all entries"


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
    assert len(lines) == expected_remaining_entries, (
        "Expected 2 remaining entries after excluding middle one"
    )
    checksums = []
    for line in lines:
        data = json.loads(line)
        checksums.append(data["sum_blake3"])
    assert "checksum_0" in checksums, "Expected checksum_0 to remain"
    assert "checksum_2" in checksums, "Expected checksum_2 to remain"
    assert "checksum_1" not in checksums, "Expected checksum_1 to be excluded"


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

    assert len(discovered) == 1, (
        "Expected 1 discovered file despite stale persisted entry"
    )
    content = persist_path.read_text(encoding="utf-8").strip()
    assert content == "", "Expected stale entry to be removed"


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

    assert len(discovered) == 1, (
        "Expected 1 discovered file despite expired persisted entry"
    )
    content = persist_path.read_text(encoding="utf-8").strip()
    assert content == "", "Expected expired entry to be removed"


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

    with patch("spectrumx.api.uploads.log_user_warning") as mock_warn:
        persist_path.parent.chmod(0o555)
        try:
            await upload_workload._persistence_manager.remove_persisted_upload(
                str(file_path.resolve())
            )
            mock_warn.assert_called()
        finally:
            persist_path.parent.chmod(0o755)


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
    assert len(remaining_lines) == 1, (
        "Expected 1 remaining entry after removing matching checksums"
    )
    remaining_data = json.loads(remaining_lines[0])
    assert remaining_data["sum_blake3"] == "checksum_to_keep", (
        "Expected non-matching checksum to remain"
    )


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
    assert content == "", "Expected empty file after removing all matching checksums"


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
    assert len(file1_lines) == 1, "Expected 1 remaining entry in file1"
    assert "other" in file1_lines[0], "Expected non-matching entry to remain"
    file2_content = persist_file2.read_text(encoding="utf-8").strip()
    assert file2_content == "", "Expected file2 to be emptied"


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

        with patch("spectrumx.api.uploads.log_user_warning") as mock_warn:
            persist_file.chmod(0o000)
            try:
                UploadPersistenceManager.remove_persisted_uploads_by_checksum(
                    checksum="some_checksum"
                )
                mock_warn.assert_called()
            finally:
                persist_file.chmod(0o644)


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

        with patch("spectrumx.api.uploads.log_user_warning") as mock_warn:
            uploads_dir.chmod(0o555)
            try:
                UploadPersistenceManager.remove_persisted_uploads_by_checksum(
                    checksum="checksum"
                )
                mock_warn.assert_called()
            finally:
                uploads_dir.chmod(0o755)


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
    assert len(remaining_lines) == expected_count, "Expected 2 remaining entries"

    checksums = [json.loads(line)["sum_blake3"] for line in remaining_lines]
    assert "checksum_a" in checksums, "Expected checksum_a to remain"
    assert "checksum_c" in checksums, "Expected checksum_c to remain"
    assert "checksum_b" not in checksums, "Expected checksum_b to be removed"


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
    assert persist_file.read_text(encoding="utf-8") == "", (
        "Expected empty file content unchanged"
    )


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
    assert len(lines) == 1, "Expected 1 non-empty line after skipping empty lines"
    assert "checksum" in lines[0], "Expected checksum in remaining line"
