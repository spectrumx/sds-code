from __future__ import annotations

import httpx
import pytest
from sds_federation.services.registry_challenge import hash_registry_challenge_token

from tests.conftest import build_registry_root_app


@pytest.mark.asyncio
async def test_internal_capabilities_requires_bearer(
    test_site_config,
    admin_token: str,
) -> None:
    app = build_registry_root_app(test_site_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        unauth = await client.get("/internal/registry/capabilities")
        assert unauth.status_code == 401
        wrong = await client.get(
            "/internal/registry/capabilities",
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert wrong.status_code == 401
        ok = await client.get(
            "/internal/registry/capabilities",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["site_fqdn"] == test_site_config.site.fqdn
        assert body["publish_enabled"] is False


@pytest.mark.asyncio
async def test_internal_capabilities_503_when_token_unset(
    test_site_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEDERATION_SYNC_ADMIN_TOKEN", raising=False)
    app = build_registry_root_app(test_site_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/internal/registry/capabilities",
            headers={"Authorization": "Bearer anything"},
        )
        assert response.status_code == 503


@pytest.mark.asyncio
async def test_internal_verify_success(
    test_site_config,
    admin_token: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sds_federation.services.well_known import build_site_document

    raw = "verify-me"
    monkeypatch.setenv("FEDERATION_REGISTRY_CHALLENGE_TOKEN", raw)

    async def _local_fetch(fqdn: str, config, **_kwargs: object):
        return build_site_document(config)

    monkeypatch.setattr(
        "sds_federation.routes.internal_registry.fetch_well_known_json",
        _local_fetch,
    )
    app = build_registry_root_app(test_site_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/internal/registry/verify",
            headers={"Authorization": f"Bearer {admin_token}"},
            json={
                "fqdn": "localhost",
                "challenge_hash": hash_registry_challenge_token(raw),
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["well_known"]["fqdn"] == "localhost"
