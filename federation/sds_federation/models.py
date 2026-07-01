import os
import tomllib
from pathlib import Path

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import Field


class SiteInfo(BaseModel):
    name: str
    fqdn: str
    display_name: str
    sync_service_url: AnyHttpUrl | None = None


class PeerInfo(BaseModel):
    name: str
    fqdn: str
    display_name: str
    gateway_api_base: AnyHttpUrl
    sync_service_url: AnyHttpUrl
    ca_cert_path: str = ""
    gateway_export_api_key: str = ""


class FederationConfig(BaseModel):
    site: SiteInfo
    peers: list[PeerInfo] = Field(default_factory=list)
    gateway_api_base: AnyHttpUrl
    sync_service_url: AnyHttpUrl


def load_federation_config() -> FederationConfig:
    path = Path(os.environ.get("FEDERATION_CONFIG_PATH", "federation.toml"))
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    gateway_base = os.environ.get(
        "GATEWAY_INTERNAL_BASE_URL",
        os.environ.get("GATEWAY_API_BASE_URL"),
    )
    if not gateway_base:
        site_table = data.get("site", {})
        fqdn = site_table.get("fqdn", "localhost")
        gateway_base = f"http://{fqdn}/api/v1"
    site_table = data.get("site", {})
    fqdn = site_table.get("fqdn", "localhost")
    sync_url = os.environ.get("FEDERATION_SYNC_SERVICE_URL") or site_table.get(
        "sync_service_url",
    )
    if not sync_url:
        sync_url = f"http://{fqdn}/sync/"
    return FederationConfig.model_validate(
        {
            **data,
            "gateway_api_base": gateway_base.rstrip("/"),
            "sync_service_url": str(sync_url).rstrip("/"),
        },
    )
