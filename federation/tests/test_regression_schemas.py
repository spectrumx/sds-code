"""Regression: Pydantic webhook/export contracts and peer URL helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.services.peer_sync import peer_webhook_url
from sds_federation.testing.sample_data import TEST_CAPTURE_UUID
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_capture_doc
from sds_federation.testing.sample_data import sample_federated_dataset_doc


@pytest.mark.regression
def test_federated_dataset_doc_rejects_unknown_fields() -> None:
    base = sample_federated_dataset_doc().model_dump()
    base["extra_gateway_field"] = "nope"
    with pytest.raises(Exception):
        FederatedDatasetDoc.model_validate(base)


@pytest.mark.regression
def test_asset_updated_webhook_round_trip_dataset() -> None:
    asset = sample_federated_dataset_doc(site_name="crc")
    payload = AssetUpdatedWebhook(
        event_type="updated",
        timestamp=datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC),
        site_name="crc",
        asset=asset,
        asset_type=AssetTypeEnum.DATASET,
    )
    restored = AssetUpdatedWebhook.model_validate(payload.model_dump(mode="json"))
    assert restored.asset is not None
    assert restored.asset.uuid == TEST_DATASET_UUID


@pytest.mark.regression
def test_asset_updated_webhook_round_trip_capture() -> None:
    asset = sample_federated_capture_doc(site_name="crc")
    payload = AssetUpdatedWebhook(
        event_type="created",
        timestamp=datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC),
        site_name="crc",
        asset=asset,
        asset_type=AssetTypeEnum.CAPTURE,
    )
    restored = AssetUpdatedWebhook.model_validate(payload.model_dump(mode="json"))
    assert isinstance(restored.asset, FederatedCaptureDoc)
    assert restored.asset.uuid == TEST_CAPTURE_UUID


@pytest.mark.regression
def test_peer_webhook_url_strips_trailing_slash() -> None:
    class Peer:
        sync_service_url = "https://example.test/sync/"

    url = peer_webhook_url(Peer(), "/webhook/dataset-updated")
    assert url == "https://example.test/sync/api/v1/webhook/dataset-updated"
