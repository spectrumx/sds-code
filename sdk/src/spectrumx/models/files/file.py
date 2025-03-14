"""File model for SpectrumX."""

from datetime import datetime
from multiprocessing import RLock
from multiprocessing.synchronize import RLock as RLockT
from pathlib import Path
from pathlib import PurePosixPath
from typing import Annotated

from pydantic import ConfigDict
from pydantic import Field

from spectrumx import utils
from spectrumx.models.base import SDSModel
from spectrumx.models.files.permission import PermissionRepresentation
from spectrumx.models.files.permission import UnixPermissionStr


class File(SDSModel):
    """A file in SDS.

    Attributes:
        # shared attributes with SDS
        created_at:         The timestamp when the file was created.
        directory:          The path to the file, relative to the user storage in SDS.
        expiration_date:    The date when the file will be marked for deletion from SDS.
        media_type:         The MIME type of the file.
        name:               The user-defined name for this file.
        permissions:        The permissions for the file.
        size:               The size of the file in bytes.
        sum_blake3:         The BLAKE3 checksum of the file.
        updated_at:         The timestamp when the file was last updated.
        uuid:               The unique identifier of the file in SDS.

        # local attributes:
        is_sample:          Sample files are not written to disk (used in dry-run mode)
        local_path:         The path to the file on the local filesystem (includes name)
    """

    created_at: datetime
    directory: Annotated[PurePosixPath, Field(default_factory=PurePosixPath)]
    expiration_date: datetime | None
    media_type: str
    name: str
    permissions: UnixPermissionStr
    size: int
    updated_at: datetime

    is_sample: bool = False
    local_path: Path | None = None

    # events and state
    _is_downloading: bool = False
    _is_uploading: bool = False
    contents_lock: RLockT = Field(default_factory=RLock, exclude=True)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def model_post_init(self, _) -> None:
        """Post-initialization steps."""

    @property
    def path(self) -> PurePosixPath:
        """Returns the path to the file, relative to the owner's root on SDS."""
        return self.directory / self.name

    @property
    def is_local(self) -> bool:
        """Checks if the file contents are available locally."""
        if self._is_downloading:
            return False
        return (
            self.local_path is not None
            and self.local_path.exists()
            and self.local_path.is_file()
        )

    def compute_sum_blake3(self) -> str | None:
        """Calculates the BLAKE3 checksum of the file.

        If the file is currently being downloaded, this method will
            block until the download is complete or terminated.

        Args:
            block: when True, waits until the file contents are unlocked.
        Returns:
            The BLAKE3 checksum of the file,
                OR None if the file is not available locally.
        """
        # we deliberately don't cache the checksum because the file
        # might be changed externally by a different process or the user.
        with self.contents_lock:
            # content downloads cannot start within this block
            if not self.is_local:
                return None
            # this should not happen anyway, so let's just assert
            assert self.local_path is not None, "Local path is not set"
            return utils.sum_blake3(self.local_path)

    @property
    def chmod_props(self) -> str:
        """Converts human-readable permissions to chmod properties."""
        return self.model_dump(
            include={"permissions": True},
            context={"mode": PermissionRepresentation.OCTAL},
        )["permissions"]

    def is_same_contents(self, other: "File", *, verbose: bool = False) -> bool:
        """Checks if the file has the same contents as another local file."""
        this_sum = self.compute_sum_blake3()
        other_sum = other.compute_sum_blake3()
        if verbose:
            utils.log_user(f"{this_sum}  {self.local_path}")
            utils.log_user(f"{other_sum}  {other.local_path}")
        return this_sum == other_sum


class FileUpload(SDSModel):
    name: str | None
    directory: str
    media_type: str
    permissions: UnixPermissionStr | None

    @staticmethod
    def from_file(file: File) -> "FileUpload":
        return FileUpload(
            name=file.name,
            directory=str(file.directory),
            media_type=file.media_type,
            permissions=file.permissions,
        )


__all__ = ["File", "FileUpload"]
