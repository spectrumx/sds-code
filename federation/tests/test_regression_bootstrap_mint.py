"""Regression tests for gateway export Api-Key mint at bootstrap."""

from __future__ import annotations

import os

import httpx
import pytest
from sds_federation.services.bootstrap import ensure_local_export_api_key
from sds_federation.services.bootstrap import mint_api_key_url
from sds_federation.services.bootstrap import mint_local_export_api_key


@pytest.mark.regression
def test_mint_api_key_url_strips_api_v1() -> None:
    assert (
        mint_api_key_url("http://gateway:8000/api/v1")
        == "http://gateway:8000/users/get-federation-sync-api-key/"
    )
    assert (
        mint_api_key_url("http://gateway:8000/api/v1/")
        == "http://gateway:8000/users/get-federation-sync-api-key/"
    )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ensure_uses_existing_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FEDERATION_SYNC_SERVER_API_KEY", "already-set.raw")
    monkeypatch.setenv("FEDERATION_SYNC_DRF_TOKEN", "should-not-be-used")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        key = await ensure_local_export_api_key(http, "http://gateway:8000/api/v1")

    assert key == "already-set.raw"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_ensure_mints_when_env_key_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("FEDERATION_SYNC_SERVER_API_KEY", raising=False)
    monkeypatch.setenv("FEDERATION_SYNC_DRF_TOKEN", "a" * 40)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).endswith("/users/get-federation-sync-api-key/")
        assert request.headers["Authorization"] == f"Token {'a' * 40}"
        return httpx.Response(
            200,
            json={
                "api_key": "minted.key.value",
                "email": "federation-sync@internal.local",
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        key = await ensure_local_export_api_key(http, "http://gateway:8000/api/v1")

    assert key == "minted.key.value"
    assert os.environ["FEDERATION_SYNC_SERVER_API_KEY"] == "minted.key.value"


@pytest.mark.regression
@pytest.mark.asyncio
async def test_mint_local_export_api_key_rejects_empty_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"api_key": ""})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(ValueError, match="missing api_key"):
            await mint_local_export_api_key(
                http,
                "http://gateway:8000/api/v1",
                drf_token="tok",  # noqa: S106
            )
