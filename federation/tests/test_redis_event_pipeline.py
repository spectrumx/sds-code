"""Isolated sync tests: simulated Redis payload → OpenSearch read → peer webhook."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime

import httpx
import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederationEventType
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.services.local_events import dispatch_federation_redis_payload
from sds_federation.services.local_events import parse_redis_event_payload
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
    asset_type, event_type, uuid, _ts = parsed
    assert event_type == FederationEventType.UPDATED
    assert uuid == TEST_DATASET_UUID
    assert asset_type.value == "dataset"


@pytest.mark.asyncio
async def test_invalid_redis_payload_ignored() -> None:
    assert parse_redis_event_payload({"item_type": "file"}) is None
    assert parse_redis_event_payload({"item_type": "dataset"}) is None
    assert (
        parse_redis_event_payload(
            {
                **simulated_dataset_redis_payload(),
                "event_type": "not-a-real-event",
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
    assert body["event_type"] == "updated"


@pytest.mark.asyncio
async def test_dispatch_deleted_uses_opensearch_or_tombstone(
    test_site_config,
    recording_opensearch,
    peer_webhook_recorder,
) -> None:
    recorded, transport = peer_webhook_recorder
    indexer = FederatedAssetIndexer(recording_opensearch)
    payload = simulated_dataset_redis_payload(event_type="deleted")

    async with httpx.AsyncClient(transport=transport) as http:
        await dispatch_federation_redis_payload(
            http,
            test_site_config,
            recording_opensearch,
            indexer,
            payload,
        )

    assert recording_opensearch.update_calls == []
    assert len(recorded) == 1
    body = json.loads(recorded[0].content.decode())
    assert body["event_type"] == "deleted"
    assert body["asset"]["uuid"] == str(TEST_DATASET_UUID)
    assert body["asset"]["name"] == ""


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
