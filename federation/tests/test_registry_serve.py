from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sds_federation.models import FederationConfig
from sds_federation.models import RegistryPolicy
from sds_federation.models import RegistryPublishPolicy
from sds_federation.models import SiteInfo
from sds_federation.services.registry_publish import publish_manifest

from tests.conftest import build_registry_root_app
from tests.test_registry_sign import write_ed25519_keypair


def _published_config(tmp_path: Path) -> FederationConfig:
    private_path, _ = write_ed25519_keypair(tmp_path)
    manifest_dir = tmp_path / "manifest"
    config = FederationConfig(
        site=SiteInfo(
            name="crc",
            fqdn="sds.crc.nd.edu",
            display_name="CRC",
        ),
        gateway_api_base="https://sds.crc.nd.edu/api/v1",
        sync_service_url="https://sds.crc.nd.edu/sync",
        peers=[],
        registry=RegistryPolicy(
            publish=RegistryPublishPolicy(
                enabled=True,
                signing_key_path=str(private_path),
                manifest_dir=str(manifest_dir),
            ),
        ),
    )
    publish_manifest(config, [], None, dry_run=False)
    return config


@pytest.mark.asyncio
async def test_registry_manifest_routes_return_bytes(tmp_path: Path) -> None:
    config = _published_config(tmp_path)
    app = build_registry_root_app(config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        manifest = await client.get("/.well-known/sds-registry/sites.json")
        sig = await client.get("/.well-known/sds-registry/sites.json.sig")
    assert manifest.status_code == 200
    assert manifest.headers["cache-control"] == "public, max-age=60"
    assert manifest.headers["content-type"].startswith("application/json")
    assert sig.status_code == 200
    assert sig.headers["content-type"].startswith("text/plain")
    assert len(manifest.content) > 10
    assert len(sig.content) > 10


@pytest.mark.asyncio
async def test_registry_manifest_404_when_publish_disabled(tmp_path: Path) -> None:
    config = _published_config(tmp_path)
    config.registry.publish.enabled = False
    app = build_registry_root_app(config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/.well-known/sds-registry/sites.json")
    assert response.status_code == 404
