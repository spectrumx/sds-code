"""Regression tests for fed_search OpenSearch reads."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_search import load_federated_asset
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.support.mock_opensearch import RecordingOpenSearch


def test_load_federated_asset_returns_indexed_doc() -> None:
    opensearch = RecordingOpenSearch()
    site = "testsite"
    doc = sample_federated_dataset_doc(site_name=site)
    FederatedAssetIndexer(opensearch).apply_asset_event(
        event_at=datetime.now(UTC),
        site_name=site,
        asset=doc,
        asset_type=AssetTypeEnum.DATASET,
    )

    loaded = load_federated_asset(
        opensearch,
        site_name=site,
        uuid=TEST_DATASET_UUID,
        asset_type=AssetTypeEnum.DATASET,
    )

    assert loaded is not None
    assert loaded.name == doc.name
    assert loaded.uuid == TEST_DATASET_UUID


def test_load_federated_asset_missing_returns_none() -> None:
    opensearch = RecordingOpenSearch()
    assert (
        load_federated_asset(
            opensearch,
            site_name="testsite",
            uuid=TEST_DATASET_UUID,
            asset_type=AssetTypeEnum.DATASET,
        )
        is None
    )
