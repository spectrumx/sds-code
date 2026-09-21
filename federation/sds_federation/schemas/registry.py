from __future__ import annotations

from datetime import UTC
from datetime import datetime
from enum import StrEnum

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import Field
from pydantic import computed_field

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
    ca_cert_file: str = ""
    client_cert_fingerprints: list[str] = Field(default_factory=list)

    def sync_service_url(self):
        return f"https://{self.fqdn}/sync"
    
    def sync_service_url(self):
        return f"https://{self.fqdn}/api/v1"


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
