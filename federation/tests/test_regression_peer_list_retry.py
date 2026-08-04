"""Regression: peer sync list fetch retries transient connection failures."""

from __future__ import annotations

from unittest.mock import AsyncMock
from unittest.mock import patch

import httpx
import pytest
from sds_federation.models import PeerInfo
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.bootstrap import _is_retryable_peer_list_error
from sds_federation.services.bootstrap import fetch_peer_sync_list
from sds_federation.testing.sample_data import sample_federated_dataset_doc


def _peer() -> PeerInfo:
    return PeerInfo(
        name="peer",
        fqdn="peer.local",
        display_name="Peer",
        gateway_api_base="http://unused:8000/api/v1",
        sync_service_url="http://sds-federation-peer-sync:8000/sync",
    )


def test_connect_error_is_retryable() -> None:
    assert _is_retryable_peer_list_error(httpx.ConnectError("boom")) is True
    assert _is_retryable_peer_list_error(httpx.ReadTimeout("slow")) is True
    req = httpx.Request("GET", "http://example/sync/api/v1/webhook/list-datasets/")
    resp = httpx.Response(503, request=req)
    assert _is_retryable_peer_list_error(
        httpx.HTTPStatusError("x", request=req, response=resp)
    )
    resp_400 = httpx.Response(400, request=req)
    assert (
        _is_retryable_peer_list_error(
            httpx.HTTPStatusError("x", request=req, response=resp_400),
        )
        is False
    )


@pytest.mark.asyncio
async def test_fetch_peer_sync_list_retries_then_succeeds() -> None:
    doc = sample_federated_dataset_doc(site_name="peer.local")
    calls = {"n": 0}

    async def flaky_get_json(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            raise httpx.ConnectError("All connection attempts failed")
        return [doc.model_dump(mode="json")]

    with (
        patch(
            "sds_federation.services.bootstrap._get_json",
            new=AsyncMock(side_effect=flaky_get_json),
        ),
        patch("sds_federation.services.bootstrap.asyncio.sleep", new=AsyncMock()),
    ):
        docs = await fetch_peer_sync_list(
            httpx.AsyncClient(),
            _peer(),
            AssetTypeEnum.DATASET,
            attempts=5,
            backoff_secs=0.01,
        )

    assert calls["n"] == 3
    assert len(docs) == 1
    assert docs[0].site_name == "peer.local"


@pytest.mark.asyncio
async def test_fetch_peer_sync_list_exhausts_retries() -> None:
    with (
        patch(
            "sds_federation.services.bootstrap._get_json",
            new=AsyncMock(side_effect=httpx.ConnectError("down")),
        ),
        patch("sds_federation.services.bootstrap.asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(httpx.ConnectError):
            await fetch_peer_sync_list(
                httpx.AsyncClient(),
                _peer(),
                AssetTypeEnum.DATASET,
                attempts=3,
                backoff_secs=0.01,
            )
