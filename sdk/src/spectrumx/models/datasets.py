"""Dataset model for SpectrumX."""

from datetime import datetime
from typing import Any

from pydantic import UUID4
from pydantic import BaseModel
from pydantic import ConfigDict

from spectrumx.models.captures import CaptureType
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.user import UserSharePermission
from spectrumx.models.user import User
from spectrumx.models.user import UserSharePermission


class DatasetFile(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uuid: UUID4 | None = None
    name: str | None = None
    directory: str | None = None
    media_type: str | None = None

class DatasetCapture(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uuid: UUID4 | None = None
    name: str | None = None
    capture_type: CaptureType | None = None
    index_name: str | None = None
    origin: CaptureOrigin | None = None
    top_level_dir: str | None = None
    owner: User | None = None

class Dataset(BaseModel):
    """A dataset in SDS."""

    model_config = ConfigDict(extra="ignore")

    uuid: UUID4 | None = None
    owner: User | None = None
    name: str | None = None
    abstract: str | None = None
    description: str | None = None
    doi: str | None = None
    authors: list[str] | None = None
    license: str | None = None
    keywords: list[str] | None = None
    institutions: list[str] | None = None
    release_date: datetime | None = None
    repository: str | None = None
    version: int | None = None
    website: str | None = None
    provenance: dict[str, Any] | None = None
    citation: dict[str, Any] | None = None
    other: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_deleted: bool = False
    is_public: bool = False
    is_shared: bool = False
    is_shared_with_me: bool = False
    share_permissions: list[UserSharePermission] | None = None
    captures: list[DatasetCapture] | None = None
    files: list[DatasetFile] | None = None


__all__ = [
    "Dataset",
    "DatasetCapture",
    "DatasetFile",
]
