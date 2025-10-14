"""Pydantic models for file system items."""

import uuid
from typing import Annotated
from typing import Literal

from pydantic import AfterValidator
from pydantic import BaseModel
from pydantic import Field
from pydantic.types import UUID4

from sds_gateway.api_methods.models import PermissionLevel


def validate_uuid_or_empty(value: str) -> str:
    """Validate UUID4 string or allow empty string."""
    if value == "":
        return value
    # This will raise ValueError if not a valid UUID4
    uuid.UUID(value, version=4)
    return value


class SharedUser(BaseModel):
    """Represents a user with whom an item is shared."""

    name: str
    email: str
    type: Literal["user"]
    permission_level: PermissionLevel


class SharedGroup(BaseModel):
    """Represents a group with whom an item is shared."""

    name: str
    email: str  # Format: "group:{uuid}"
    type: Literal["group"]
    permission_level: PermissionLevel
    members: list[str] = Field(default_factory=list)
    member_count: int = 0


# Union type for shared users and groups
SharedEntity = SharedUser | SharedGroup


class BaseItem(BaseModel):
    """Base item model for file system items."""

    type: Literal["file", "directory", "capture", "dataset"]
    name: str
    path: str
    uuid: UUID4 | Annotated[str, AfterValidator(validate_uuid_or_empty)] = ""
    modified_at: str | None = None


class FileItem(BaseItem):
    """File item model."""

    type: Literal["file"] = "file"
    is_shared: bool = False
    capture_uuid: UUID4 | Annotated[str, AfterValidator(validate_uuid_or_empty)] = ""
    shared_by: str = ""
    description: str = ""

    @property
    def is_h5_file(self) -> bool:
        """Check if this file is an HDF5 file based on extension."""
        name_lower = self.name.lower()
        return name_lower.endswith((".h5", ".hdf5"))


class DirectoryItem(BaseItem):
    """Directory item model."""

    type: Literal["directory"] = "directory"
    item_count: int = 0
    is_shared: bool = False
    is_capture: bool = False  # True if this directory represents a capture
    shared_by: str = ""


class CaptureItem(BaseItem):
    """Capture item model."""

    type: Literal["capture"] = "capture"
    is_owner: bool = True
    is_shared_with_me: bool = False
    owner_name: str = ""
    owner_email: str = ""
    shared_users: list[SharedEntity] = Field(default_factory=list)


class DatasetItem(BaseItem):
    """Dataset item model."""

    type: Literal["dataset"] = "dataset"
    is_owner: bool = True
    is_shared_with_me: bool = False
    owner_name: str = ""
    owner_email: str = ""
    shared_users: list[SharedEntity] = Field(default_factory=list)


# Union type for all items
Item = FileItem | DirectoryItem | CaptureItem | DatasetItem
