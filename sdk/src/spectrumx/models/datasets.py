"""Dataset model for SpectrumX."""

from datetime import datetime
from typing import Any

from pydantic import UUID4
from pydantic import BaseModel


class Dataset(BaseModel):
    """A dataset in SDS."""

    # TODO ownership: include ownership and access level information

    uuid: UUID4 | None = None
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
    version: str | None = None
    website: str | None = None
    provenance: dict[str, Any] | None = None
    citation: dict[str, Any] | None = None
    other: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    is_deleted: bool = False
    is_public: bool = False


__all__ = [
    "Dataset",
]
