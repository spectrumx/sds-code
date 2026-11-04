from __future__ import annotations

import httpx
import pytest

from tests.conftest import build_registry_root_app


@pytest.mark.asyncio
async def test_internal_paths_not_under_sync_mount(
    test_site_config,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FEDERATION_SYNC_ADMIN_TOKEN", "secret")
    app = build_registry_root_app(test_site_config)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        sync_cap = await client.get(
            "/sync/internal/registry/capabilities",
            headers={"Authorization": "Bearer secret"},
        )
        sync_api = await client.get(
            "/sync/api/v1/internal/registry/capabilities",
            headers={"Authorization": "Bearer secret"},
        )
    assert sync_cap.status_code == 404
    assert sync_api.status_code == 404
