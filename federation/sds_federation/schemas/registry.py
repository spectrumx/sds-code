from __future__ import annotations

from datetime import UTC
from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator

REGISTRY_SCHEMA_VERSION = 1


class SiteStatusEnum(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"


class RegistrySite(BaseModel):
    name: str
    fqdn: str
    display_name: str
    status: SiteStatusEnum = SiteStatusEnum.ACTIVE
    gateway_api_base: AnyHttpUrl
    sync_service_url: AnyHttpUrl
    ca_cert_file: str = ""
    client_cert_fingerprints: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def default_service_urls_from_fqdn(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        fqdn = data.get("fqdn")
        if not fqdn:
            return data
        out = dict(data)
        if not out.get("gateway_api_base"):
            out["gateway_api_base"] = f"https://{fqdn}/api/v1"
        if not out.get("sync_service_url"):
            out["sync_service_url"] = f"https://{fqdn}/sync"
        return out


class RegistryManifest(BaseModel):
    schema_version: int
    serial: int = Field(ge=0)
    issued_at: datetime
    expires_at: datetime
    sites: list[RegistrySite] = Field(default_factory=list)

    def is_expired(self, *, now: datetime | None = None) -> bool:
        return (now or datetime.now(UTC)) >= self.expires_at

    def active_sites(self) -> list[RegistrySite]:
        return [s for s in self.sites if s.status is SiteStatusEnum.ACTIVE]
