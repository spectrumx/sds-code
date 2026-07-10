"""Integration: simulated Redis dispatch → OpenSearch read → peer webhook."""

from __future__ import annotations

import json

import httpx
import pytest
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.services.local_events import dispatch_federation_redis_payload
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import simulated_dataset_redis_payload

from tests.conftest import PEER_SYNC_BASE
from tests.support.mock_opensearch import RecordingOpenSearch


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_simulation_end_to_end_indexes_on_peer(
    test_site_config,
    stub_dataset_resolver,
    peer_webhook_stack,
) -> None:
    recording_opensearch, asgi_transport = peer_webhook_stack
    local_opensearch = RecordingOpenSearch()
    stub_dataset_resolver(local_opensearch)
    indexer = FederatedAssetIndexer(local_opensearch)
    payload = simulated_dataset_redis_payload()
    local_calls_before = len(local_opensearch.index_calls)

    async with httpx.AsyncClient(
        transport=asgi_transport, base_url=PEER_SYNC_BASE
    ) as http:
        dispatched = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            local_opensearch,
            indexer,
            payload,
        )

    assert dispatched is True
    assert len(local_opensearch.index_calls) == local_calls_before
    assert len(recording_opensearch.index_calls) == 1
    assert recording_opensearch.index_calls[0]["id"] == doc_id(
        "testsite",
        TEST_DATASET_UUID,
    )
    assert (
        recording_opensearch.index_calls[0]["body"]["name"]
        == "Simulated public dataset"
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_subscriber_path_parses_and_dispatches(
    test_site_config,
    stub_dataset_resolver,
    peer_webhook_stack,
) -> None:
    """Same bytes as Redis pub/sub would deliver (json.loads once)."""
    recording_opensearch, asgi_transport = peer_webhook_stack
    local_opensearch = RecordingOpenSearch()
    stub_dataset_resolver(local_opensearch)
    indexer = FederatedAssetIndexer(local_opensearch)
    raw = json.dumps(simulated_dataset_redis_payload())

    async with httpx.AsyncClient(
        transport=asgi_transport, base_url=PEER_SYNC_BASE
    ) as http:
        ok = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            local_opensearch,
            indexer,
            json.loads(raw),
        )

    assert ok is True
    assert len(recording_opensearch.index_calls) == 1
