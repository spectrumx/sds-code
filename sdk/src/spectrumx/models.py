"""Data models for the SpectrumX Data System SDK."""

from datetime import date
from datetime import datetime
from pathlib import Path

from pydantic import UUID4
from pydantic import BaseModel

from . import utils


class SDSModel(BaseModel):
    """Base class for most models in SDS."""

    uuid: UUID4 | None = None


class File(SDSModel):
    """A file in SDS.

    Attributes:
        # shared attributes with SDS
        uuid:               The unique identifier of the file in SDS.
        created_at:         The timestamp when the file was created.
        directory:          The path to the file, relative to the user storage in SDS.
        expiration_date:    The date when the file will be marked for deletion from SDS.
        media_type:         The MIME type of the file.
        name:               The user-defined name for this file.
        permissions:        The permissions for the file.
        size:               The size of the file in bytes.
        updated_at:         The timestamp when the file was last updated.

        # local attributes:
        is_sample:          Sample files are not written to disk (used in dry-run mode).
        local_path:         The path to the file on the local filesystem.
    """

    created_at: datetime
    directory: Path
    expiration_date: date | None
    media_type: str
    name: str
    permissions: str
    size: int
    updated_at: datetime

    is_sample: bool = False
    local_path: Path | None = None

    @property
    def path(self) -> str:
        """Returns the path to the file, relative to the owner's root on SDS."""
        return f"{self.directory}/{self.name}"

    @property
    def chmod_props(self) -> str:
        """Converts human-readable permissions to chmod properties."""
        utils.validate_file_permission_string(self.permissions)
        one_hot = "".join(["0" if flag == "-" else "1" for flag in self.permissions])
        perm_num = int(one_hot, base=2)
        max_permission_num = 0o777
        assert 0 <= perm_num <= max_permission_num, "Invalid permission number"
        return f"{perm_num:03o}"


class Dataset(SDSModel):
    """A dataset in SDS (collection of files)."""

    # TODO: Implement this model.


class Capture(SDSModel):
    """A capture in SDS (collection of related RF files)."""

    # TODO: Implement this model.


__all__ = [
    "Capture",
    "Dataset",
    "File",
    "SDSModel",
]
