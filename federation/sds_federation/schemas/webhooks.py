from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field


class FederationEventType(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


class AssetTypeEnum(StrEnum):
    DATASET = "dataset"
    CAPTURE = "capture"

    @property
    def export_path(self) -> str:
        return f"/federation/export/{self.value}s/"

    @property
    def webhook_path(self) -> str:
        return f"/webhook/{self.value}-updated"

    @property
    def doc_class(self) -> type[BaseModel]:
        if self == AssetTypeEnum.DATASET:
            return FederatedDatasetDoc
        return FederatedCaptureDoc

    @property
    def index_name(self) -> str:
        return f"fed-{self.value}s"


class FederatedDatasetDoc(BaseModel):
    """Must match gateway DatasetFederationSerializer output keys exactly."""

    model_config = ConfigDict(extra="forbid")

    uuid: UUID
    name: str
    status: str
    status_display: str
    abstract: str = ""
    description: str = ""
    doi: str = ""
    authors: list[Any] = Field(default_factory=list)
    license: str = ""
    keywords: list[str] = Field(default_factory=list)
    institutions: list[Any] = Field(default_factory=list)
    release_date: str | None = None
    repository: str = ""
    version: int = 1
    website: str = ""
    provenance: dict[str, Any] | list[Any] | None = None
    citation: dict[str, Any] | list[Any] | None = None
    other: dict[str, Any] | list[Any] | None = None
    created_at: str | None = None
    is_public: bool = False
    owner_name: str = ""
    updated_at: str | None = None
    site_name: str
    size: int = 0
    capture_count: int = 0
    capture_file_count: int = 0
    artifact_file_count: int = 0


class FederatedCaptureDoc(BaseModel):
    """Must match gateway CaptureFederationSerializer output keys exactly."""

    model_config = ConfigDict(extra="forbid")

    uuid: UUID
    name: str = ""
    capture_type: str
    channel: str = ""
    scan_group: UUID | str | None = None
    top_level_dir: str = ""
    created_at: str | None = None
    updated_at: str | None = None
    site_name: str
    file_count: int = 0
    size: int = 0
    capture_props: dict[str, Any] = Field(default_factory=dict)
    dataset_ids: list[str] = Field(default_factory=list)


class AssetUpdatedWebhook(BaseModel):
    event_type: FederationEventType
    timestamp: datetime
    site_name: str
    asset: FederatedDatasetDoc | FederatedCaptureDoc | None = None
    asset_type: AssetTypeEnum


class SiteHelloWebhook(BaseModel):
    """Remote sync registration after bootstrap."""

    model_config = ConfigDict(extra="forbid")

    site_name: str
    fqdn: str
    display_name: str = ""
    sync_service_url: AnyHttpUrl
    timestamp: datetime | None = None
