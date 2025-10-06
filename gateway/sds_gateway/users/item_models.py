"""Pydantic models for file system items."""

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class BaseItem(BaseModel):
    """Base item model for file system items."""

    type: Literal["file", "directory", "capture", "dataset"]
    name: str
    path: str
    uuid: str
    modified_at: str | None = None


class FileItem(BaseItem):
    """File item model."""

    type: Literal["file"] = "file"
    is_capture: bool = False
    is_shared: bool = False
    capture_uuid: str = ""
    shared_by: str = ""
    description: str = ""


class DirectoryItem(BaseItem):
    """Directory item model."""

    type: Literal["directory"] = "directory"
    item_count: int | None = None
    is_shared: bool = False
    shared_by: str = ""


class CaptureItem(BaseItem):
    """Capture item model."""

    type: Literal["capture"] = "capture"
    is_owner: bool = True
    is_shared_with_me: bool = False
    owner_name: str = ""
    owner_email: str = ""
    shared_users: list[dict[str, Any]] = Field(default_factory=list)


class DatasetItem(BaseItem):
    """Dataset item model."""

    type: Literal["dataset"] = "dataset"
    is_owner: bool = True
    is_shared_with_me: bool = False
    owner_name: str = ""
    owner_email: str = ""
    shared_users: list[dict[str, Any]] = Field(default_factory=list)


# Union type for all items
Item = FileItem | DirectoryItem | CaptureItem | DatasetItem
