import os
import tomllib
from pathlib import Path
from typing import Self

from pydantic import AnyHttpUrl
from pydantic import BaseModel
from pydantic import Field
from pydantic import model_validator


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


def site_name_for_federation(site: SiteInfo | PeerInfo) -> str:
    """FQDN stored in export docs and OpenSearch ``site_name`` (RFC §6)."""
    return site.fqdn


class RegistryPolicy(BaseModel):
    url: AnyHttpUrl | None = None
    public_key_path: str = ""
    certs_dir: str = "/etc/sds/certs"
    cache_dir: str = "/var/lib/sds/registry"
    refresh_secs: int = 900
    required: bool = False
    deny: list[str] = Field(default_factory=list)


class FederationConfig(BaseModel):
    site: SiteInfo
    peers: list[PeerInfo] = Field(default_factory=list)
    # Snapshot of [[peers]] at load; registry merge seeds from this, not mutable peers.
    static_peers: list[PeerInfo] = Field(default_factory=list)
    registry: RegistryPolicy = Field(default_factory=RegistryPolicy)
    gateway_api_base: AnyHttpUrl
    sync_service_url: AnyHttpUrl

    @model_validator(mode="after")
    def _ensure_static_peers_snapshot(self) -> Self:
        if not self.static_peers and self.peers:
            self.static_peers = [peer.model_copy(deep=True) for peer in self.peers]
        return self


def snapshot_runtime_peers(config: FederationConfig) -> list[PeerInfo]:
    """Copy of the live peer list for iteration across await points."""
    return list(config.peers)


def allowed_federated_origin_fqdns(config: FederationConfig) -> set[str]:
    return {peer.fqdn for peer in snapshot_runtime_peers(config)} | {config.site.fqdn}


def _registry_policy(data: dict) -> RegistryPolicy:
    table = dict(data.get("registry", {}))
    for key, env in (
        ("url", "FEDERATION_REGISTRY_URL"),
        ("public_key_path", "FEDERATION_REGISTRY_PUBKEY_PATH"),
        ("cache_dir", "FEDERATION_REGISTRY_CACHE_DIR"),
    ):
        value = os.environ.get(env, "").strip()
        if value:
            table[key] = value
    return RegistryPolicy.model_validate(table)


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
            "registry": _registry_policy(data),
            "gateway_api_base": gateway_base.rstrip("/"),
            "sync_service_url": str(sync_url).rstrip("/"),
        },
    )
