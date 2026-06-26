"""Integration tests using the two-site in-process federation mesh."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime

import pytest
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.services.bootstrap import bootstrap_gateway_exports
from sds_federation.services.bootstrap import push_site_hello_to_peer
from sds_federation.services.bootstrap import register_with_peers
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.services.local_events import dispatch_federation_redis_payload
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc
from sds_federation.testing.sample_data import simulated_dataset_redis_payload

from tests.support.federation_mesh import FederationMesh
from tests.support.federation_mesh import TESTSITE_GATEWAY_HOST


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mesh_dispatches_redis_event_to_peer_opensearch(
    two_site_mesh: FederationMesh,
    test_site_config,
    stub_dataset_resolver,
) -> None:
    mesh = two_site_mesh
    payload = simulated_dataset_redis_payload()
    local = mesh.site("testsite")
    indexer = FederatedAssetIndexer(local.opensearch)
    ok = await dispatch_federation_redis_payload(
        mesh.http,
        test_site_config,
        indexer,
        payload,
        resolve_asset=stub_dataset_resolver,
    )
    assert ok is True
    assert len(local.opensearch.index_calls) == 1
    assert local.opensearch.index_calls[0]["id"] == doc_id(
        "testsite",
        TEST_DATASET_UUID,
    )
    peer = mesh.site("peer-one")
    assert len(peer.opensearch.index_calls) == 1
    assert peer.opensearch.index_calls[0]["id"] == doc_id(
        "testsite",
        TEST_DATASET_UUID,
    )
    assert len(mesh.recorded_webhooks) == 1
    body = json.loads(mesh.recorded_webhooks[0].content.decode())
    webhook = AssetUpdatedWebhook.model_validate(body)
    assert webhook.site_name == "testsite"
    assert webhook.asset is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mesh_site_hello_registers_on_peer_registry(
    two_site_mesh: FederationMesh,
) -> None:
    mesh = two_site_mesh
    caller = mesh.site("testsite")
    peer = mesh.site("peer-one")
    result = await push_site_hello_to_peer(
        mesh.http,
        caller.config.peers[0],
        caller.config,
    )
    assert result["status"] == "registered"
    assert peer.registry.get("testsite") is not None
    assert len(peer.registry.registration_events) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mesh_register_with_peers_both_directions(
    two_site_mesh: FederationMesh,
) -> None:
    mesh = two_site_mesh
    await register_with_peers(mesh.http, mesh.site("testsite").config)
    await register_with_peers(mesh.http, mesh.site("peer-one").config)
    assert mesh.site("peer-one").registry.get("testsite") is not None
    assert mesh.site("testsite").registry.get("peer-one") is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mesh_bootstrap_pulls_gateway_export_catalog(
    two_site_mesh: FederationMesh,
) -> None:
    mesh = two_site_mesh
    doc = sample_federated_dataset_doc(site_name="testsite")
    mesh.gateway_catalog.set_datasets(TESTSITE_GATEWAY_HOST, [doc])
    peer = mesh.site("peer-one")
    indexer = FederatedAssetIndexer(peer.opensearch)
    event_at = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    count = await bootstrap_gateway_exports(
        mesh.http,
        peer.config.peers[0],
        indexer,
        event_at=event_at,
    )
    assert count == 1
    assert peer.opensearch.index_calls[0]["id"] == doc_id(
        "testsite",
        TEST_DATASET_UUID,
    )
