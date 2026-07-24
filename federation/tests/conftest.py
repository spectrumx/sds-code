from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from fastapi import FastAPI
from sds_federation.models import FederationConfig
from sds_federation.routes.webhooks import webhooks_router
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.peer_registry import PeerRegistry
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.support.federation_mesh import PEER_ONE_SYNC_ORIGIN
from tests.support.federation_mesh import build_federation_mesh
from tests.support.federation_mesh import close_mesh
from tests.support.federation_mesh import peer_one_config
from tests.support.federation_mesh import testsite_config
from tests.support.mock_opensearch import RecordingOpenSearch

if TYPE_CHECKING:
    from tests.support.mock_peer_registry import RecordingPeerRegistry

API_PREFIX = "/api/v1"
SYNC_API_PREFIX = f"/sync{API_PREFIX}"
PEER_SYNC_BASE = PEER_ONE_SYNC_ORIGIN


def make_peer_config(*, site_name: str = "peer-one") -> FederationConfig:
    """Receiver sync: allows webhooks whose site_name is listed in peers."""
    config = peer_one_config()
    if site_name != "peer-one":
        return config.model_copy(
            update={
                "site": config.site.model_copy(update={"name": site_name}),
            },
        )
    return config


def build_webhook_app(
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
    registry: PeerRegistry | RecordingPeerRegistry | None = None,
) -> FastAPI:
    reg = registry or PeerRegistry()
    sync_app = FastAPI()
    sync_app.state.config = config
    sync_app.state.fed_indexer = indexer
    sync_app.state.peer_registry = reg
    sync_app.include_router(webhooks_router, prefix=API_PREFIX)
    root = FastAPI()
    root.mount("/sync", sync_app)
    root.state.peer_registry = sync_app.state.peer_registry
    return root


@pytest.fixture
def recording_opensearch() -> RecordingOpenSearch:
    return RecordingOpenSearch()


@pytest.fixture
def test_site_config() -> FederationConfig:
    return testsite_config()


def seed_federated_dataset_in_opensearch(
    opensearch: RecordingOpenSearch,
    site_name: str,
    *,
    uuid=TEST_DATASET_UUID,
) -> None:
    """Simulate gateway having indexed a public dataset into fed-datasets."""
    doc = sample_federated_dataset_doc(site_name=site_name, uuid=uuid)
    FederatedAssetIndexer(opensearch).apply_asset_event(
        event_at=datetime.now(UTC),
        site_name=site_name,
        asset=doc,
        asset_type=AssetTypeEnum.DATASET,
    )


@pytest.fixture
def stub_dataset_resolver(test_site_config: FederationConfig):
    """Deprecated name: seeds OpenSearch instead of resolving via HTTP export."""

    def _seed(recording_opensearch: RecordingOpenSearch) -> None:
        seed_federated_dataset_in_opensearch(
            recording_opensearch,
            test_site_config.site.name,
        )

    return _seed


@pytest.fixture
async def two_site_mesh():
    mesh = build_federation_mesh()
    yield mesh
    await close_mesh(mesh)


@pytest.fixture
def peer_webhook_recorder():
    """httpx transport that records outbound peer webhook POSTs."""
    recorded: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return httpx.Response(200, json={"status": "accepted"})

    transport = httpx.MockTransport(handler)
    return recorded, transport


@pytest.fixture
def peer_webhook_stack(recording_opensearch: RecordingOpenSearch):
    """In-process peer sync app + httpx client (ASGI) + OpenSearch recorder."""
    config = make_peer_config()
    indexer = FederatedAssetIndexer(recording_opensearch)
    app = build_webhook_app(config, indexer)
    transport = httpx.ASGITransport(app=app)
    return recording_opensearch, transport
