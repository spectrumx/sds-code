"""Isolated sync tests: simulated Redis payload → stub asset → peer webhook."""

from __future__ import annotations

import json

import httpx
import pytest
from sds_federation.services.local_events import dispatch_federation_redis_payload
from sds_federation.services.local_events import parse_redis_event_payload
from sds_federation.services.peer_sync import peer_webhook_url
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import simulated_dataset_redis_payload


@pytest.mark.asyncio
async def test_parse_simulated_redis_payload() -> None:
    data = simulated_dataset_redis_payload()
    parsed = parse_redis_event_payload(data)
    assert parsed is not None
    asset_type, event_type, uuid, _ts = parsed
    assert event_type == "updated"
    assert uuid == TEST_DATASET_UUID
    assert asset_type.value == "dataset"


@pytest.mark.asyncio
async def test_invalid_redis_payload_ignored() -> None:
    assert parse_redis_event_payload({"item_type": "file"}) is None
    assert parse_redis_event_payload({"item_type": "dataset"}) is None


@pytest.mark.asyncio
async def test_dispatch_resolves_uuid_and_posts_webhook_to_peer(
    test_site_config,
    stub_dataset_resolver,
    peer_webhook_recorder,
) -> None:
    recorded, transport = peer_webhook_recorder
    payload = simulated_dataset_redis_payload()

    async with httpx.AsyncClient(transport=transport) as http:
        dispatched = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            payload,
            resolve_asset=stub_dataset_resolver,
        )

    assert dispatched is True
    assert len(recorded) == 1
    req = recorded[0]
    expected_url = peer_webhook_url(
        test_site_config.peers[0],
        "/webhook/dataset-updated",
    )
    assert str(req.url) == expected_url
    body = json.loads(req.content.decode())
    assert body["site_name"] == "testsite"
    assert body["asset_type"] == "dataset"
    assert body["asset"]["uuid"] == str(TEST_DATASET_UUID)
    assert body["asset"]["name"] == "Simulated public dataset"
    assert body["event_type"] == "updated"


@pytest.mark.asyncio
async def test_dispatch_deleted_skips_resolver_and_sends_tombstone(
    test_site_config,
    stub_dataset_resolver,
    peer_webhook_recorder,
) -> None:
    recorded, transport = peer_webhook_recorder
    payload = simulated_dataset_redis_payload(event_type="deleted")

    async def fail_if_called(*_args, **_kwargs):
        raise AssertionError("gateway/stub fetch must not run for deleted events")

    async with httpx.AsyncClient(transport=transport) as http:
        await dispatch_federation_redis_payload(
            http,
            test_site_config,
            payload,
            resolve_asset=fail_if_called,
        )

    assert len(recorded) == 1
    body = json.loads(recorded[0].content.decode())
    assert body["event_type"] == "deleted"
    assert body["asset"]["uuid"] == str(TEST_DATASET_UUID)
    assert body["asset"]["name"] == ""


@pytest.mark.asyncio
async def test_dispatch_unknown_uuid_resolver_raises(
    test_site_config,
    stub_dataset_resolver,
    peer_webhook_recorder,
) -> None:
    _, transport = peer_webhook_recorder
    payload = simulated_dataset_redis_payload(
        uuid="00000000-0000-0000-0000-000000000099",
    )

    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(KeyError, match="no stub document"):
            await dispatch_federation_redis_payload(
                http,
                test_site_config,
                payload,
                resolve_asset=stub_dataset_resolver,
            )
