"""Integration: simulated Redis dispatch → outbound POST → peer webhook → OpenSearch."""

from __future__ import annotations

import httpx
import pytest
from sds_federation.services.fed_index import doc_id
from sds_federation.services.local_events import dispatch_federation_redis_payload
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import simulated_dataset_redis_payload

from tests.conftest import PEER_SYNC_BASE


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_simulation_end_to_end_indexes_on_peer(
    test_site_config,
    stub_dataset_resolver,
    peer_webhook_stack,
) -> None:
    recording_opensearch, asgi_transport = peer_webhook_stack
    payload = simulated_dataset_redis_payload()

    async with httpx.AsyncClient(
        transport=asgi_transport, base_url=PEER_SYNC_BASE
    ) as http:
        dispatched = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            payload,
            resolve_asset=stub_dataset_resolver,
        )

    assert dispatched is True
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
    import json

    from sds_federation.services.local_events import dispatch_federation_redis_payload

    recording_opensearch, asgi_transport = peer_webhook_stack
    raw = json.dumps(simulated_dataset_redis_payload())

    async with httpx.AsyncClient(
        transport=asgi_transport, base_url=PEER_SYNC_BASE
    ) as http:
        ok = await dispatch_federation_redis_payload(
            http,
            test_site_config,
            json.loads(raw),
            resolve_asset=stub_dataset_resolver,
        )

    assert ok is True
    assert len(recording_opensearch.index_calls) == 1
