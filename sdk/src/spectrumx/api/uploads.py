"""Resumable file upload workloads for the SpectrumX SDK."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC
from datetime import datetime
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Annotated
from typing import NoReturn

from loguru import logger as log
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
from spectrumx.utils import log_user
from spectrumx.utils import log_user_warning

upload_prog_bar_kwargs = {
    "desc": "Discovering files...",  # placeholder before upload starts
    "disable": False,  # prog bar is not initialized properly if True
    "unit": "B",
    "unit_scale": True,
    "unit_divisor": 1024,
}

if TYPE_CHECKING:
    from collections.abc import Iterable


class UploadedFile(BaseModel):
    """Represents a file that was successfully uploaded in a resumable upload."""

    sds_file: File
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class SkippedUpload(BaseModel):
    """Represents a filesystem entry that was skipped during discovery."""

    path: Path
    reasons: tuple[str, ...] = Field(default_factory=tuple)


class UploadWorkload(BaseModel):
    """Serializable representation of an upload workload."""

    client: "Client" = Field(exclude=True)  # noqa: UP037
    local_root: Annotated[Path, Field(alias="local_path")]
    sds_path: PurePosixPath = Field(default_factory=lambda: PurePosixPath("/"))
    max_concurrent_uploads: int = 5

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
    _prog_uploaded_bytes: tqdm[NoReturn] | None = None

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }

    def model_post_init(self, context) -> None:
        """Initialize the workload with an async lock."""
        self._state_lock = asyncio.Lock()
        if self.verbose:
            self._prog_uploaded_bytes = get_prog_bar(
                total=self.total_bytes,
                **upload_prog_bar_kwargs,
                leave=True,
            )
            self._prog_uploaded_bytes.disable = True
            self._prog_uploaded_bytes.clear()
        super().model_post_init(context)

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
            msg = f"Upload root not found: {root}"
            raise FileNotFoundError(msg)
        if not root.is_dir():
            msg = f"Upload root is not a directory: {root}"
            raise NotADirectoryError(msg)

        await self._reset_state()
        self.discovery_started_at = datetime.now(UTC)

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
            is_valid, reasons = file_ops.is_valid_file(
                file_path=candidate,
                check_sds_ignore=check_sds_ignore,
            )
            file_candidate_progress.update(1)
            if not is_valid:
                skipped = SkippedUpload(path=candidate, reasons=tuple(reasons))
                await self._add_skipped(skipped)
                if self.warn_skipped:
                    log_user_warning(f"Skipping {candidate}:")
                    for reason in reasons:
                        log_user_warning(f"  - {reason}")
                continue

            file_model = create_file_instance(root=root, candidate=candidate)
            await self._register_discovered_file(file_model)

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

    async def _mark_completed(self, sds_file: File) -> None:
        """Mark a file as successfully uploaded."""
        async with self._state_lock:
            self._remove_from_buffer(sds_file, self.fq_in_progress)
            if sds_file not in self.fq_completed:
                self.fq_completed.append(sds_file)
        await self._update_prog_bars(num_bytes=sds_file.size)

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
        return (
            f"{prefix}{len(self.fq_completed):,} done"
            f" + {len(self.fq_failed):,} fail"
            f" + {len(self.fq_in_progress):,} act"
            f" + {len(self.fq_skipped):,} skpd"
            f" / {len(self.fq_discovered):,} total"
        )

    async def _mark_failed(self, sds_file: File, reason: str | None = None) -> None:
        """Mark a file upload as failed and record the reason."""
        async with self._state_lock:
            self._remove_from_buffer(sds_file, self.fq_in_progress)
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
                    sds_path=next_file.directory,
                )
            )
            await self._mark_completed(next_file)
        except SDSError as err:
            await self._mark_failed(sds_file=next_file, reason=str(err))
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
            log.error(skipped)
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

        results = [Result(value=file) for file in self.fq_completed]
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
) -> list[Result[File]]:
    """Uploads files to SDS using resumable concurrent uploads.

    Args:
        client:                    The SpectrumX client.
        local_path:                The path to the local directory to upload.
        sds_path:                  The destination path in SDS.
        max_concurrent_uploads:    Maximum number of concurrent upload workers.
        verbose:                   Whether to print verbose output.
        warn_skipped:              Whether to warn when a file is skipped.

    Returns:
        A list of Result objects for each uploaded file.
    """

    local_path = Path(local_path) if isinstance(local_path, str) else local_path

    upload_workload = UploadWorkload(
        client=client,
        local_root=local_path.parent,
        sds_path=PurePosixPath(sds_path),
        max_concurrent_uploads=max_concurrent_uploads,
        verbose=verbose,
        warn_skipped=warn_skipped,
    )

    return asyncio.run(upload_workload.run(client=client))
