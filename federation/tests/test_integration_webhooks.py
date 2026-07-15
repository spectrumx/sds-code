"""Integration tests: FastAPI webhook routes + app state."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.conftest import SYNC_API_PREFIX
from tests.conftest import build_webhook_app
from tests.conftest import make_peer_config

if TYPE_CHECKING:
    from tests.support.mock_opensearch import RecordingOpenSearch


def _dataset_webhook_payload(*, site_name: str = "testsite") -> dict:
    asset = sample_federated_dataset_doc(site_name=site_name)
    webhook = AssetUpdatedWebhook(
        timestamp=datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC),
        site_name=site_name,
        asset=asset,
        asset_type=AssetTypeEnum.DATASET,
    )
    return webhook.model_dump(mode="json")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_dataset_webhook_indexes_via_http(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"{SYNC_API_PREFIX}/webhook/dataset-updated",
            json=_dataset_webhook_payload(site_name="testsite"),
        )

    assert response.status_code == 200
    assert response.json() == {"status": "accepted"}
    assert len(recording_opensearch.index_calls) == 1
    assert (
        recording_opensearch.index_calls[0]["index"] == AssetTypeEnum.DATASET.index_name
    )
    assert recording_opensearch.index_calls[0]["id"] == doc_id(
        "testsite",
        TEST_DATASET_UUID,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_rejects_unknown_origin_site(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"{SYNC_API_PREFIX}/webhook/dataset-updated",
            json=_dataset_webhook_payload(site_name="unknown-site"),
        )

    assert response.status_code == 403
    assert recording_opensearch.index_calls == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_rejects_local_site_name(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"{SYNC_API_PREFIX}/webhook/dataset-updated",
            json=_dataset_webhook_payload(site_name=config.site.name),
        )

    assert response.status_code == 403
    assert recording_opensearch.index_calls == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_webhook_rejects_site_name_mismatch_on_asset(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))
    body = _dataset_webhook_payload(site_name="testsite")
    body["asset"]["site_name"] = "mismatch"

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            f"{SYNC_API_PREFIX}/webhook/dataset-updated",
            json=body,
        )

    assert response.status_code == 422
    assert recording_opensearch.index_calls == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_site_hello_registers_known_peer(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))
    body = {
        "site_name": "testsite",
        "fqdn": "localhost",
        "display_name": "Originating test site",
        "sync_service_url": "http://testsite.test/sync",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(f"{SYNC_API_PREFIX}/webhook/site-hello", json=body)

    assert response.status_code == 200
    assert response.json() == {"status": "registered", "site_name": "testsite"}
    assert app.state.peer_registry.get("testsite") is not None


@pytest.mark.integration
@pytest.mark.asyncio
async def test_site_hello_rejects_unknown_site(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))
    body = {
        "site_name": "unknown",
        "fqdn": "evil.test",
        "sync_service_url": "http://evil.test/sync",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(f"{SYNC_API_PREFIX}/webhook/site-hello", json=body)

    assert response.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_site_hello_rejects_self_registration(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    config = make_peer_config()
    app = build_webhook_app(config, FederatedAssetIndexer(recording_opensearch))
    body = {
        "site_name": "peer-one",
        "fqdn": "peer.test",
        "sync_service_url": "http://peer-one.test/sync",
    }

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(f"{SYNC_API_PREFIX}/webhook/site-hello", json=body)

    assert response.status_code == 422
