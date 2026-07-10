"""Regression tests for FederatedAssetIndexer (OpenSearch write behavior)."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

if TYPE_CHECKING:
    from tests.support.mock_opensearch import RecordingOpenSearch


@pytest.mark.regression
def test_doc_id_format() -> None:
    assert doc_id("crc", TEST_DATASET_UUID) == f"crc:{TEST_DATASET_UUID}"


@pytest.mark.regression
def test_indexer_writes_dataset_document(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    indexer = FederatedAssetIndexer(recording_opensearch)
    event_at = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    asset = sample_federated_dataset_doc(site_name="testsite")

    indexer.apply_asset_event(
        event_at=event_at,
        site_name="testsite",
        asset=asset,
        asset_type=AssetTypeEnum.DATASET,
    )

    assert len(recording_opensearch.index_calls) == 1
    call = recording_opensearch.index_calls[0]
    assert call["index"] == AssetTypeEnum.DATASET.index_name
    assert call["id"] == doc_id("testsite", TEST_DATASET_UUID)
    assert call["body"]["federation_event_at"] == event_at.isoformat()
    assert call["body"]["name"] == "Simulated public dataset"
    assert call["body"]["is_deleted"] is False


@pytest.mark.regression
def test_indexer_writes_deleted_flag_from_asset_body(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    indexer = FederatedAssetIndexer(recording_opensearch)
    event_at = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    asset = sample_federated_dataset_doc(site_name="testsite").model_copy(
        update={"is_deleted": True},
    )

    indexer.apply_asset_event(
        event_at=event_at,
        site_name="testsite",
        asset=asset,
        asset_type=AssetTypeEnum.DATASET,
    )

    assert len(recording_opensearch.index_calls) == 1
    assert recording_opensearch.update_calls == []
    assert recording_opensearch.index_calls[0]["body"]["is_deleted"] is True


@pytest.mark.regression
def test_indexer_skips_stale_events(recording_opensearch: RecordingOpenSearch) -> None:
    indexer = FederatedAssetIndexer(recording_opensearch)
    asset = sample_federated_dataset_doc(site_name="testsite")
    t1 = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    t0 = t1 - timedelta(seconds=1)

    indexer.apply_asset_event(
        event_at=t1,
        site_name="testsite",
        asset=asset,
        asset_type=AssetTypeEnum.DATASET,
    )
    indexer.apply_asset_event(
        event_at=t0,
        site_name="testsite",
        asset=asset,
        asset_type=AssetTypeEnum.DATASET,
    )

    assert len(recording_opensearch.index_calls) == 1


@pytest.mark.regression
def test_indexer_rejects_site_name_mismatch(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    indexer = FederatedAssetIndexer(recording_opensearch)
    asset = sample_federated_dataset_doc(site_name="other-site")

    with pytest.raises(ValueError, match="site_name must match"):
        indexer.apply_asset_event(
            event_at=datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC),
            site_name="testsite",
            asset=asset,
            asset_type=AssetTypeEnum.DATASET,
        )
