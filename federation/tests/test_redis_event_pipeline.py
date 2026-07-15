"""Isolated sync tests: simulated Redis payload → OpenSearch read → peer webhook."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime

import httpx
import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.local_events import dispatch_federation_redis_payload
from sds_federation.services.local_events import parse_redis_event_payload
from sds_federation.services.peer_registry import PeerRegistry
from sds_federation.services.peer_sync import peer_webhook_url
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc
from sds_federation.testing.sample_data import simulated_dataset_redis_payload

from tests.conftest import seed_federated_dataset_in_opensearch


@pytest.mark.asyncio
async def test_parse_simulated_redis_payload() -> None:
    data = simulated_dataset_redis_payload()
    parsed = parse_redis_event_payload(data)
    assert parsed is not None
    asset_type, uuid, _ts = parsed
    assert uuid == TEST_DATASET_UUID
    assert asset_type.value == "dataset"


@pytest.mark.asyncio
async def test_invalid_redis_payload_ignored() -> None:
    assert parse_redis_event_payload({"item_type": "file"}) is None
    assert parse_redis_event_payload({"item_type": "dataset"}) is None
    assert (
        parse_redis_event_payload(
            {
                "item_type": "dataset",
                "uuid": "not-a-uuid",
                "timestamp": "2026-06-11T12:00:00+00:00",
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_dispatch_reads_opensearch_and_posts_webhook_to_peer(
    test_site_config,
    recording_opensearch,
    peer_webhook_recorder,
) -> None:
    recorded, transport = peer_webhook_recorder
    seed_federated_dataset_in_opensearch(
        recording_opensearch,
        test_site_config.site.name,
    )
    calls_before = len(recording_opensearch.index_calls)
    indexer = FederatedAssetIndexer(recording_opensearch)
    payload = simulated_dataset_redis_payload()

    async with httpx.AsyncClient(transport=transport) as http:
        dispatched = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            recording_opensearch,
            indexer,
            payload,
        )

    assert dispatched is True
    assert len(recording_opensearch.index_calls) == calls_before
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
    assert "event_type" not in body


@pytest.mark.asyncio
async def test_dispatch_deleted_doc_from_opensearch(
    test_site_config,
    recording_opensearch,
    peer_webhook_recorder,
) -> None:
    recorded, transport = peer_webhook_recorder
    doc = sample_federated_dataset_doc(
        site_name=test_site_config.site.name,
    ).model_copy(update={"is_deleted": True})
    FederatedAssetIndexer(recording_opensearch).apply_asset_event(
        event_at=datetime.now(UTC),
        site_name=test_site_config.site.name,
        asset=doc,
        asset_type=AssetTypeEnum.DATASET,
    )
    indexer = FederatedAssetIndexer(recording_opensearch)
    payload = simulated_dataset_redis_payload()

    async with httpx.AsyncClient(transport=transport) as http:
        await dispatch_federation_redis_payload(
            http,
            test_site_config,
            recording_opensearch,
            indexer,
            payload,
        )

    assert len(recorded) == 1
    body = json.loads(recorded[0].content.decode())
    assert body["asset"]["is_deleted"] is True
    assert body["asset"]["uuid"] == str(TEST_DATASET_UUID)


@pytest.mark.asyncio
async def test_dispatch_missing_opensearch_doc_skips_peer_push(
    test_site_config,
    recording_opensearch,
    peer_webhook_recorder,
) -> None:
    recorded, transport = peer_webhook_recorder
    indexer = FederatedAssetIndexer(recording_opensearch)
    payload = simulated_dataset_redis_payload(
        uuid="00000000-0000-0000-0000-000000000099",
    )

    async with httpx.AsyncClient(transport=transport) as http:
        dispatched = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            recording_opensearch,
            indexer,
            payload,
        )

    assert dispatched is True
    assert recorded == []


@pytest.mark.asyncio
async def test_dispatch_uses_registry_sync_url_overlay(
    test_site_config,
    recording_opensearch,
) -> None:
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json={"status": "accepted"})

    seed_federated_dataset_in_opensearch(
        recording_opensearch,
        test_site_config.site.name,
    )
    peer = test_site_config.peers[0]
    registry = PeerRegistry()
    registry.register(
        SiteHelloWebhook(
            site_name=peer.name,
            fqdn=peer.fqdn,
            display_name=peer.display_name,
            sync_service_url="http://overlay-sync.test/sync",
            timestamp=datetime.now(UTC),
        ),
    )
    indexer = FederatedAssetIndexer(recording_opensearch)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        await dispatch_federation_redis_payload(
            http,
            test_site_config,
            recording_opensearch,
            indexer,
            simulated_dataset_redis_payload(),
            registry=registry,
        )

    assert len(recorded) == 1
    assert str(recorded[0].url) == (
        "http://overlay-sync.test/sync/api/v1/webhook/dataset-updated"
    )
    assert str(recorded[0].url) != peer_webhook_url(peer, "/webhook/dataset-updated")
