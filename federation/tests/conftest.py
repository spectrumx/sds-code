from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from sds_federation.models import FederationConfig
from sds_federation.models import PeerInfo
from sds_federation.models import SiteInfo
from sds_federation.routes.webhooks import webhooks_router
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.local_events import AssetResolver
from sds_federation.services.peer_registry import PeerRegistry
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.support.mock_opensearch import RecordingOpenSearch

API_PREFIX = "/api/v1"
PEER_SYNC_BASE = "http://peer-sync.test"


def make_peer_config(*, site_name: str = "peer-one") -> FederationConfig:
    """Receiver sync: allows webhooks whose site_name is listed in peers."""
    return FederationConfig(
        site=SiteInfo(
            name=site_name,
            fqdn="peer.test",
            display_name="Peer Site",
        ),
        gateway_api_base="http://gateway.invalid/api/v1",
        sync_service_url="http://peer-one.test/sync",
        peers=[
            PeerInfo(
                name="testsite",
                fqdn="localhost",
                display_name="Originating test site",
                gateway_api_base="http://gateway.invalid/api/v1",
                sync_service_url="http://unused/",
            ),
        ],
    )


def build_webhook_app(
    config: FederationConfig,
    indexer: FederatedAssetIndexer,
) -> FastAPI:
    app = FastAPI()
    app.state.config = config
    app.state.fed_indexer = indexer
    app.state.peer_registry = PeerRegistry()
    app.include_router(webhooks_router, prefix=API_PREFIX)
    return app


@pytest.fixture
def recording_opensearch() -> RecordingOpenSearch:
    return RecordingOpenSearch()


@pytest.fixture
def test_site_config() -> FederationConfig:
    return FederationConfig(
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
                display_name="Peer One",
                gateway_api_base="http://peer-gateway.invalid/api/v1",
                sync_service_url=PEER_SYNC_BASE,
            ),
        ],
    )


@pytest.fixture
def stub_dataset_resolver(test_site_config: FederationConfig) -> AssetResolver:
    docs: dict[str, FederatedDatasetDoc] = {
        str(TEST_DATASET_UUID): sample_federated_dataset_doc(
            site_name=test_site_config.site.name,
        ),
    }

    async def resolve(
        _http: httpx.AsyncClient,
        config: FederationConfig,
        uuid,
        asset_type: AssetTypeEnum,
    ) -> FederatedDatasetDoc:
        if asset_type != AssetTypeEnum.DATASET:
            msg = f"stub resolver only supports datasets, got {asset_type}"
            raise ValueError(msg)
        doc = docs.get(str(uuid))
        if doc is None:
            msg = f"no stub document for uuid {uuid}"
            raise KeyError(msg)
        if doc.site_name != config.site.name:
            return doc.model_copy(update={"site_name": config.site.name})
        return doc

    return resolve


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
