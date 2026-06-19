"""Integration tests for bootstrap export pull and site-hello registration."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from sds_federation.models import FederationConfig
from sds_federation.models import PeerInfo
from sds_federation.models import SiteInfo
from sds_federation.services.bootstrap import bootstrap_gateway_exports
from sds_federation.services.bootstrap import push_site_hello_to_peer
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.conftest import make_peer_config

if TYPE_CHECKING:
    from tests.support.mock_opensearch import RecordingOpenSearch


@pytest.mark.integration
@pytest.mark.asyncio
async def test_bootstrap_gateway_exports_indexes_documents(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    doc = sample_federated_dataset_doc(site_name="remote")
    export_body = json.dumps([doc.model_dump(mode="json")])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "export/datasets" in str(request.url):
            return httpx.Response(200, content=export_body.encode())
        if request.method == "GET" and "export/captures" in str(request.url):
            return httpx.Response(200, json=[])
        return httpx.Response(404)

    peer = PeerInfo(
        name="remote",
        fqdn="remote.test",
        display_name="Remote",
        gateway_api_base="http://remote-gateway.test/api/v1",
        sync_service_url="http://remote-sync.test",
    )
    indexer = FederatedAssetIndexer(recording_opensearch)
    event_at = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        count = await bootstrap_gateway_exports(
            http,
            peer,
            indexer,
            event_at=event_at,
        )

    assert count == 1
    assert len(recording_opensearch.index_calls) == 1
    assert recording_opensearch.index_calls[0]["id"] == doc_id(
        "remote",
        TEST_DATASET_UUID,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_push_site_hello_to_in_process_peer(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    from tests.conftest import PEER_SYNC_BASE
    from tests.conftest import build_webhook_app

    peer_sync_url = f"{PEER_SYNC_BASE}/sync"

    peer_config = make_peer_config()
    app = build_webhook_app(peer_config, FederatedAssetIndexer(recording_opensearch))
    caller_config = FederationConfig(
        site=SiteInfo(
            name="testsite",
            fqdn="localhost",
            display_name="Test Site",
        ),
        gateway_api_base="http://gateway.invalid/api/v1",
        sync_service_url="http://testsite.test/sync",
        peers=[
            PeerInfo(
                name="peer-one",
                fqdn="peer.test",
                display_name="Peer",
                gateway_api_base="http://gateway.invalid/api/v1",
                sync_service_url=peer_sync_url,
            ),
        ],
    )
    peer = caller_config.peers[0]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url=peer_sync_url,
    ) as http:
        result = await push_site_hello_to_peer(http, peer, caller_config)

    assert result["status"] == "registered"
    assert app.state.peer_registry.get("testsite") is not None
