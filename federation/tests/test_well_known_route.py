from __future__ import annotations

import httpx
import pytest
from sds_federation.models import FederationConfig
from sds_federation.models import SiteInfo

from tests.conftest import build_registry_root_app


GATEWAY_WELL_KNOWN_KEYS = frozenset(
    {
        "schema_version",
        "name",
        "fqdn",
        "display_name",
        "gateway_api_base",
        "sync_service_url",
        "registry_challenge",
        "registry_url",
        "registry_pubkey_fingerprint",
        "contact",
    },
)


def _config_with_site(**site_kwargs: object) -> FederationConfig:
    site = SiteInfo(
        name="fed1",
        fqdn="sds-fed1.crc.nd.edu",
        display_name="Fed1 test peer",
        **site_kwargs,
    )
    return FederationConfig(
        site=site,
        gateway_api_base="http://127.0.0.1:9/api/v1",
        sync_service_url="https://sds-fed1.crc.nd.edu/sync",
        peers=[],
    )


@pytest.mark.asyncio
async def test_well_known_fields_from_site_config() -> None:
    config = _config_with_site(
        gateway_api_base="https://sds-fed1.crc.nd.edu/api/v1",
        sync_service_url="https://sds-fed1.crc.nd.edu/sync",
    )
    app = build_registry_root_app(config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/.well-known/sds-federation.json")
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "no-store"
    doc = response.json()
    assert doc["name"] == "fed1"
    assert doc["fqdn"] == "sds-fed1.crc.nd.edu"
    assert doc["gateway_api_base"] == "https://sds-fed1.crc.nd.edu/api/v1"
    assert doc["sync_service_url"] == "https://sds-fed1.crc.nd.edu/sync"
    assert "registry_challenge" not in doc


@pytest.mark.asyncio
async def test_well_known_includes_challenge_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEDERATION_REGISTRY_CHALLENGE_TOKEN", "plain-token")
    app = build_registry_root_app(_config_with_site())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/.well-known/sds-federation.json")
    assert response.json()["registry_challenge"] == "plain-token"


@pytest.mark.asyncio
async def test_well_known_503_when_site_incomplete() -> None:
    config = FederationConfig(
        site=SiteInfo(name="", fqdn="", display_name=""),
        gateway_api_base="http://127.0.0.1:9/api/v1",
        sync_service_url="https://example.edu/sync",
        peers=[],
    )
    app = build_registry_root_app(config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/.well-known/sds-federation.json")
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_well_known_key_set_matches_gateway_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEDERATION_REGISTRY_CHALLENGE_TOKEN", "t")
    monkeypatch.setenv("FEDERATION_REGISTRY_WELL_KNOWN_URL", "https://x/registry")
    monkeypatch.setenv("FEDERATION_REGISTRY_PUBKEY_FINGERPRINT", "sha256:abc")
    monkeypatch.setenv("SDS_FEDERATION_WELL_KNOWN_CONTACT", "ops@example.edu")
    app = build_registry_root_app(_config_with_site())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        doc = (await client.get("/.well-known/sds-federation.json")).json()
    assert set(doc) <= GATEWAY_WELL_KNOWN_KEYS
    assert set(doc) >= {
        "schema_version",
        "name",
        "fqdn",
        "display_name",
        "gateway_api_base",
        "sync_service_url",
        "registry_challenge",
        "registry_url",
        "registry_pubkey_fingerprint",
        "contact",
    }
