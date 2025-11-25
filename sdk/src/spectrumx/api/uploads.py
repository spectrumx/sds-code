"""Resumable file upload workloads for the SpectrumX SDK."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Annotated
from typing import NoReturn

from pydantic import BaseModel
from pydantic import Field
from tqdm import tqdm

from spectrumx.client import (
    Client,  # noqa: TC001
    # pydantic complains if not defined out of type checking block
)
from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.errors import UploadError
from spectrumx.models.files.file import (
    File,  # noqa: TC001
    # pydantic complains if not defined out of type checking block
)
from spectrumx.ops import files as file_ops
from spectrumx.utils import get_prog_bar
from spectrumx.utils import is_test_env
from spectrumx.utils import log_user
from spectrumx.utils import log_user_warning
from spectrumx.vendor.xdg_base_dirs import xdg_state_home

upload_prog_bar_kwargs = {
    "desc": "Discovering files...",  # placeholder before upload starts
    "disable": False,  # prog bar is not initialized properly if True
    "unit": "B",
    "unit_scale": True,
    "unit_divisor": 1024,
}

if TYPE_CHECKING:
    from collections.abc import Iterable

MAX_DAYS_FOR_RESUMING_UPLOAD = 30


class PersistedUploadFile(BaseModel):
    """Represents a file that was successfully uploaded and persisted locally.

    Allows quick resumption of uploads by tracking which files have already been
    uploaded based on their resolved path and BLAKE3 checksum.
    """

    resolved_path: Path
    sum_blake3: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class UploadedFile(BaseModel):
    """Represents a file that was successfully uploaded in a resumable upload."""

    sds_file: File
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class SkippedUpload(BaseModel):
    """Represents a filesystem entry that was skipped during discovery."""

    path: Path
    reasons: tuple[str, ...] = Field(default_factory=tuple)


class UploadPersistenceManager(BaseModel):
    """Manages persistence of uploaded file records to local storage.

    Handles all file I/O operations for tracking completed uploads to enable
    resumable uploads.
    """

    local_root: Path
    client: "Client" = Field(exclude=True)  # noqa: UP037
    persist_state: bool = True

    model_config = {
        "arbitrary_types_allowed": True,
    }

    @staticmethod
    def _get_persisted_uploads_dir() -> Path:
        """Get the directory where persisted upload records are stored."""
        state_home = xdg_state_home()
        uploads_dir = state_home / "spectrumx" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)
        return uploads_dir

    def _get_persisted_uploads_path(self) -> Path:
        """Get the path to the persistence file for this workload."""
        uploads_dir = self._get_persisted_uploads_dir()
        root_hash = hashlib.sha256(
            str(self.local_root.resolve()).encode("utf-8")
        ).hexdigest()[:8]
        return uploads_dir / f"{root_hash}_uploads.jsonl"

    @property
    def should_persist(self) -> bool:
        """Don't persist data when in dry-run mode, except in tests."""
        return not self.client.dry_run or is_test_env()

    async def load_persisted_uploads(self) -> dict[str, PersistedUploadFile]:
        """Load previously uploaded files from persistence.

        Returns:
            Dictionary mapping resolved paths to PersistedUploadFile records.
        """
        if not self.persist_state:
            return {}

        persist_path = self._get_persisted_uploads_path()
        if not persist_path.exists():
            return {}

        persisted: dict[str, PersistedUploadFile] = {}
        try:
            with persist_path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():  # pragma: no cover
                        continue
                    data = json.loads(line)
                    uploaded_file = PersistedUploadFile(**data)
                    persisted[str(uploaded_file.resolved_path)] = uploaded_file
        except (json.JSONDecodeError, ValueError) as err:
            log_user_warning(
                f"Failed to load persisted uploads; resuming might be slower: {err}"
            )
            return {}
        return persisted

    async def save_persisted_upload(self, sds_file: File) -> None:
        """Save an uploaded file to persistence.

        Args:
            sds_file: The file that was successfully uploaded.
        """
        if not self.persist_state or not sds_file.local_path:
            return

        # compute checksum if not already done
        sum_blake3 = sds_file.compute_sum_blake3()
        if not sum_blake3:
            return

        persisted_file = PersistedUploadFile(
            resolved_path=sds_file.local_path.resolve(),
            sum_blake3=sum_blake3,
        )

        persist_path = self._get_persisted_uploads_path()
        # don't persist data when in dry-run mode, except in tests
        if not self.should_persist:  # pragma: no cover
            return
        try:
            with persist_path.open("a", encoding="utf-8") as f:
                f.write(persisted_file.model_dump_json() + "\n")
        except (OSError, ValueError) as err:
            log_user_warning(f"Failed to persist uploaded file: {err}")

    async def remove_persisted_upload(self, resolved_path: str) -> None:
        """Remove an upload entry from persisted storage.

        Args:
            resolved_path: The resolved file path to remove from persistence.
        """
        if not self.persist_state:
            return

        persist_path = self._get_persisted_uploads_path()
        if not persist_path.exists():
            return

        try:
            await self._rewrite_persisted_uploads_excluding(
                persist_path=persist_path,
                excluded_paths={resolved_path},
            )
        except (OSError, ValueError, json.JSONDecodeError) as err:
            log_user_warning(f"Failed to remove persisted upload entry: {err}")

    async def _rewrite_persisted_uploads_excluding(
        self,
        persist_path: Path,
        excluded_paths: set[str],
    ) -> None:
        """Rewrite the persistence file, excluding specified paths.

        Args:
            persist_path: Path to the persistence file.
            excluded_paths: Set of resolved paths to exclude from the rewritten file.
        """
        persisted_entries: list[PersistedUploadFile] = []
        try:
            with persist_path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    uploaded_file = PersistedUploadFile(**data)
                    if str(uploaded_file.resolved_path) not in excluded_paths:
                        persisted_entries.append(uploaded_file)
        except (json.JSONDecodeError, ValueError) as err:
            log_user_warning(f"Failed to parse persisted uploads for rewrite: {err}")
            return

        # don't persist data when in dry-run mode, except in tests
        if not self.should_persist:  # pragma: no cover
            return
        # rewrite the file with remaining entries
        try:
            with persist_path.open("w", encoding="utf-8") as f:
                for entry in persisted_entries:
                    f.write(entry.model_dump_json() + "\n")
        except OSError as err:
            log_user_warning(f"Failed to rewrite persistence file: {err}")

    @staticmethod
    def remove_persisted_uploads_by_checksum(checksum: str) -> None:
        """Removes all persisted upload entries with a given checksum.

        Searches across all persistence files in the global uploads directory
        and removes any entries matching the provided checksum.

        Args:
            checksum: The BLAKE3 checksum to search for and remove.
        """
        try:
            uploads_dir = UploadPersistenceManager._get_persisted_uploads_dir()

            for persist_file in uploads_dir.glob("*_uploads.jsonl"):
                persisted_entries: list[PersistedUploadFile] = []
                try:
                    with persist_file.open(encoding="utf-8") as f:
                        for line in f:
                            if not line.strip():
                                continue
                            data = json.loads(line)
                            uploaded_file = PersistedUploadFile(**data)
                            if uploaded_file.sum_blake3 != checksum:
                                persisted_entries.append(uploaded_file)
                except (json.JSONDecodeError, ValueError, OSError) as err:
                    log_user_warning(
                        f"Failed to process persistence file {persist_file}: {err}"
                    )
                    continue

                try:
                    with persist_file.open("w", encoding="utf-8") as f:
                        for entry in persisted_entries:
                            f.write(entry.model_dump_json() + "\n")
                except OSError as err:
                    log_user_warning(
                        f"Failed to update persistence file {persist_file}: {err}"
                    )
        except OSError as err:
            log_user_warning(f"Failed to clean persisted uploads by checksum: {err}")


class UploadWorkload(BaseModel):
    """Serializable representation of an upload workload."""

    client: "Client" = Field(exclude=True)  # noqa: UP037
    local_root: Annotated[Path, Field(alias="local_path")]
    sds_path: PurePosixPath = Field(default_factory=lambda: PurePosixPath("/"))
    max_concurrent_uploads: int = 5
    persist_state: bool = True

    # file buffers
    fq_discovered: list[File] = Field(default_factory=list)
    fq_pending: list[File] = Field(default_factory=list)
    fq_in_progress: list[File] = Field(default_factory=list)
    fq_completed: list[File] = Field(default_factory=list)
    fq_failed: list[UploadError] = Field(default_factory=list)
    fq_skipped: list[SkippedUpload] = Field(default_factory=list)

    discovery_finished_at: datetime | None = None
    discovery_started_at: datetime | None = None
    total_bytes: int = 0
    verbose: bool = False
    warn_skipped: bool = True

    # progress bars
    _prog_uploaded_bytes: (
        tqdm[NoReturn] | None  # pyrefly: ignore[bad-specialization]
    ) = None
    _persistence_manager: UploadPersistenceManager | None = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    def model_post_init(self, context) -> None:
        """Initialize the workload with an async lock."""
        self._state_lock = asyncio.Lock()
        self._workload_id = self._compute_workload_id()
        self._persistence_manager = UploadPersistenceManager(
            local_root=self.local_root,
            client=self.client,
            persist_state=self.persist_state,
        )
        if self.verbose:
            self._prog_uploaded_bytes = get_prog_bar(
                total=self.total_bytes,
                **upload_prog_bar_kwargs,  # pyrefly: ignore[bad-argument-type]
                leave=True,
            )
            self._prog_uploaded_bytes.disable = True
            self._prog_uploaded_bytes.clear()
        super().model_post_init(context)

    @staticmethod
    def _compute_workload_id() -> str:
        """Compute a stable workload ID based on current time."""
        return hashlib.sha256(
            str(datetime.now(tz=UTC).isoformat()).encode()
        ).hexdigest()[:16]

    async def _process_file_candidate(
        self,
        *,
        candidate: Path,
        root: Path,
        persisted_uploads: dict[str, PersistedUploadFile],
        check_sds_ignore: bool,
    ) -> None:
        """Process a single file candidate during discovery.

        Validates the file, checks for prior uploads, and registers if needed.
        """
        is_valid, reasons = file_ops.is_valid_file(
            file_path=candidate,
            check_sds_ignore=check_sds_ignore,
        )
        if not is_valid:
            skipped = SkippedUpload(path=candidate, reasons=tuple(reasons))
            await self._add_skipped(skipped)
            if self.warn_skipped:
                log_user_warning(f"Skipping {candidate}:")
                for reason in reasons:
                    log_user_warning(f"  - {reason}")
            return

        file_model = create_file_instance(root=root, candidate=candidate)

        # skip files that have already been successfully uploaded
        resolved_path = str(candidate.resolve())
        if resolved_path in persisted_uploads:
            persisted = persisted_uploads[resolved_path]
            current_checksum = file_model.compute_sum_blake3()
            if (
                current_checksum == persisted.sum_blake3
                and (datetime.now(UTC) - persisted.uploaded_at).days
                <= MAX_DAYS_FOR_RESUMING_UPLOAD
            ):
                if self.verbose or self.warn_skipped:  # pragma: no cover
                    log_user(
                        "Skipping already uploaded: "
                        f"'{candidate.name}' ({current_checksum})"
                    )
                return
            # remove stale entry (checksum changed or entry expired)
            assert self._persistence_manager is not None
            await self._persistence_manager.remove_persisted_upload(
                resolved_path=resolved_path
            )

        await self._register_discovered_file(file_model=file_model)

    async def _discover_files(
        self,
        *,
        check_sds_ignore: bool = True,
    ) -> list[File]:
        """Discover valid files under ``local_root`` and populate buffers.

        Args:
            warn_skipped: Emit warnings for skipped paths as they are found.
            verbose: Show a progress bar and summary logging.
            check_sds_ignore: Respect .sds-ignore patterns when validating files.

        Returns:
            The list of discovered files ready for upload.
        """

        root = Path(self.local_root).expanduser().resolve()
        if not root.exists():
            msg = f"Upload root not found: '{root}'"
            raise FileNotFoundError(msg)
        if not root.is_dir():
            msg = f"Upload root is not a directory: '{root}'"
            raise NotADirectoryError(msg)

        await self._reset_state()
        self.discovery_started_at = datetime.now(UTC)

        assert self._persistence_manager is not None
        persisted_uploads = await self._persistence_manager.load_persisted_uploads()

        file_candidate_generator: Iterable[Path] = root.rglob("*")
        file_candidate_progress = get_prog_bar(
            None,
            desc="Discovering files",
            disable=not self.verbose,
            leave=True,
        )

        for candidate in file_candidate_generator:
            if not candidate.is_file():
                continue
            file_candidate_progress.update(1)
            await self._process_file_candidate(
                candidate=candidate,
                root=root,
                persisted_uploads=persisted_uploads,
                check_sds_ignore=check_sds_ignore,
            )

        self.discovery_finished_at = datetime.now(UTC)

        if self.verbose:
            log_user(
                "Prepared upload workload with "
                f"{self.total_files:,} files ({self.total_bytes_human})"
            )
            if self.fq_skipped:
                log_user_warning(
                    f"Skipped {len(self.fq_skipped)} paths during discovery"
                )

        return list(self.fq_discovered)

    @property
    def total_bytes_human(self) -> str:
        """Returns the total bytes in human-readable format."""
        use_si = True
        divider = 1000 if use_si else 1024
        suffixes = ["B", "KB", "MB", "GB", "TB", "PB"]
        size = self.total_bytes
        index = 0
        while size >= divider and index < len(suffixes) - 1:
            size /= divider
            index += 1
        return f"{size:.2f} {suffixes[index]}"

    async def _acquire_next_file(self) -> File | None:
        """Move the next pending file into the in-progress buffer."""
        async with self._state_lock:
            if not self.fq_pending:
                return None
            next_file = self.fq_pending.pop(0)
            self.fq_in_progress.append(next_file)
        await self._update_prog_bars()
        return next_file

    async def _mark_completed_result(self, successful_result: Result[File]) -> None:
        """Mark a file as successfully uploaded."""
        assert successful_result, "Result must be successful here"
        uploaded_file = successful_result()
        async with self._state_lock:
            self._remove_from_buffer(uploaded_file, self.fq_in_progress)
            if successful_result not in self.fq_completed:
                self.fq_completed.append(uploaded_file)
        assert self._persistence_manager is not None
        await self._persistence_manager.save_persisted_upload(uploaded_file)
        await self._update_prog_bars(num_bytes=uploaded_file.size)

    async def _update_prog_bars(self, num_bytes: int | None = None) -> None:
        """Update progress bars based on current upload state."""
        if self.verbose and isinstance(self._prog_uploaded_bytes, tqdm):
            async with self._state_lock:
                self._prog_uploaded_bytes.disable = False
                self._prog_uploaded_bytes.set_description(self._get_progress_string())
                if num_bytes:
                    self._prog_uploaded_bytes.update(num_bytes)

    def _get_progress_string(self) -> str:
        """Returns a progress string for the upload progress bar."""
        use_unicode = sys.platform != "win32"
        prefix = "UP | "
        if use_unicode:
            return (
                f"{prefix}{len(self.fq_completed):,} ✅ "
                f"+ {len(self.fq_failed):,} ❌ "
                f"+ {len(self.fq_in_progress):,} ⏳ "
                f"+ {len(self.fq_skipped):,} 🐇 "
                f" / {len(self.fq_discovered):,}"
            )
        # pragma: no cover
        return (
            f"{prefix}{len(self.fq_completed):,} done"
            f" + {len(self.fq_failed):,} fail"
            f" + {len(self.fq_in_progress):,} act"
            f" + {len(self.fq_skipped):,} skpd"
            f" / {len(self.fq_discovered):,} total"
        )

    async def _mark_failed_file(
        self, sds_file: File, reason: str | None = None
    ) -> None:
        """Mark a file upload as failed and record the reason."""
        async with self._state_lock:
            self._remove_from_buffer(sds_file=sds_file, buffer=self.fq_in_progress)
            failed_entry = UploadError(
                message="Upload failed",
                sds_file=sds_file,
                reason=reason,
            )
            self.fq_failed.append(failed_entry)

    async def _reset_progress(self) -> None:
        """Reset runtime buffers without discarding discovered files."""
        async with self._state_lock:
            self.fq_pending = list(self.fq_discovered)
            self.fq_in_progress.clear()
            self.fq_completed.clear()
            self.fq_failed.clear()
            if isinstance(self._prog_uploaded_bytes, tqdm):
                self._prog_uploaded_bytes.clear()

    @property
    def total_files(self) -> int:
        """Total number of files discovered in the workload."""
        return len(self.fq_discovered)

    @property
    def remaining_files(self) -> int:
        """Number of files still pending upload."""
        return len(self.fq_pending) + len(self.fq_in_progress)

    def _remaining_bytes(self) -> int:
        """Total size in bytes of files that are yet to complete."""
        uploaded_bytes = sum(sds_file.size for sds_file in self.fq_completed)
        return max(self.total_bytes - uploaded_bytes, 0)

    async def _upload_next_file(self) -> Result[File]:
        """Upload the next file in the queue."""
        next_file: File | None = await self._acquire_next_file()
        if not next_file:
            return Result(exception=StopAsyncIteration("No more files to upload"))

        try:
            result = Result(
                value=self.client._sds_files.upload_file(  # pyright: ignore[reportPrivateUsage]  # noqa: SLF001
                    client=self.client,
                    local_file=next_file,
                    sds_path=self.sds_path,
                )
            )
            await self._mark_completed_result(successful_result=result)
        except SDSError as err:
            await self._mark_failed_file(sds_file=next_file, reason=str(err))
            result = Result(
                exception=err,
                error_info={
                    "sds_file": next_file,
                    "reason": err.reason if isinstance(err, UploadError) else None,
                    "error": str(err),
                },
            )

        return result

    async def _upload_worker(self, worker_id: int) -> None:
        """Worker coroutine that processes uploads concurrently.

        Args:
            worker_id: Identifier for the worker, used for logging.
        """
        while await self._has_pending_files():
            result = await self._upload_next_file()
            if not result:
                msg = "Upload failed with unknown error"
                default_exception = RuntimeError(msg)
                log_user_warning(
                    f"Worker {worker_id}: Upload failed: "
                    f"{result.exception_or(default_exception)}"
                )

    async def _has_pending_files(self) -> bool:
        """Check if there are pending files to upload."""
        async with self._state_lock:
            return bool(self.fq_pending)

    async def _execute_uploads(self) -> None:
        """Execute uploads concurrently using worker coroutines."""
        await self._reset_progress()

        workers = [self._upload_worker(i) for i in range(self.max_concurrent_uploads)]
        await asyncio.gather(*workers)

        # close progress bar
        if isinstance(self._prog_uploaded_bytes, tqdm):
            self._prog_uploaded_bytes.close()

    async def _reset_state(self) -> None:
        """Reset all state buffers."""
        async with self._state_lock:
            self.fq_discovered.clear()
            self.fq_pending.clear()
            self.fq_in_progress.clear()
            self.fq_completed.clear()
            self.fq_failed.clear()
            self.fq_skipped.clear()
            self.total_bytes = 0

    async def _register_discovered_file(self, file_model: File) -> None:
        """Register a newly discovered file in the workload."""
        async with self._state_lock:
            self.fq_discovered.append(file_model)
            self.fq_pending.append(file_model)
            self.total_bytes += file_model.size
            if isinstance(self._prog_uploaded_bytes, tqdm):
                self._prog_uploaded_bytes.total = self.total_bytes

    async def _add_skipped(self, skipped: SkippedUpload) -> None:
        """Add a skipped file entry."""
        async with self._state_lock:
            self.fq_skipped.append(skipped)

    async def run(self, client: Client) -> list[Result[File]]:
        """Run the upload workload discovery and execute all uploads.

        Args:
            client: The SpectrumX client.

        Returns:
            List of results for each uploaded file.
        """
        self.client = client
        await self._discover_files()
        await self._execute_uploads()

        results = [Result(value=file_obj) for file_obj in self.fq_completed]
        results.extend(
            Result(
                exception=error,
                error_info={
                    "sds_file": error.sds_file,
                    "reason": error.reason,
                    "error": str(error),
                },
            )
            for error in self.fq_failed
        )

        return results

    @staticmethod
    def _remove_from_buffer(sds_file: File, buffer: list[File]) -> None:
        try:
            buffer.remove(sds_file)
        except ValueError:
            return


def create_file_instance(root: Path, candidate: Path) -> File:
    """Creates a File model instance for a given candidate path."""
    relative_parent = candidate.relative_to(root).parent
    return file_ops.construct_file(
        file_path=candidate,
        sds_path=PurePosixPath(relative_parent),
    )


def upload_resumable(
    client: Client,
    *,
    local_path: Path | str,
    sds_path: PurePosixPath | Path | str = "/",
    max_concurrent_uploads: int = 5,
    verbose: bool = True,
    warn_skipped: bool = True,
    persist_state: bool = True,
) -> list[Result[File]]:
    """Uploads files to SDS using resumable concurrent uploads.

    Args:
        client:                    The SpectrumX client.
        local_path:                The path to the local directory to upload.
        sds_path:                  The destination path in SDS.
        max_concurrent_uploads:    Maximum number of concurrent upload workers.
        verbose:                   Whether to print verbose output.
        warn_skipped:              Whether to warn when a file is skipped.
        persist_state:             Whether to persist upload state for resumption.

    Returns:
        A list of Result objects for each uploaded file.
    """

    local_path = Path(local_path) if isinstance(local_path, str) else local_path

    upload_workload = UploadWorkload(
        client=client,
        local_root=local_path,
        sds_path=PurePosixPath(sds_path),
        max_concurrent_uploads=max_concurrent_uploads,
        verbose=verbose,
        warn_skipped=warn_skipped,
        persist_state=persist_state,
    )

    return asyncio.run(upload_workload.run(client=client))
