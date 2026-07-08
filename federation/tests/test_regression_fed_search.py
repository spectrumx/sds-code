"""Regression: federated search query assembly and OpenSearch document reads."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_search import load_federated_asset
from sds_federation.services.fed_search import search_federated_datasets
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.support.mock_opensearch import RecordingOpenSearch

pytest.importorskip("sds_opensearch_query")


@pytest.mark.regression
def test_search_federated_datasets_builds_bool_query() -> None:
    client = RecordingOpenSearch()
    result = search_federated_datasets(
        client,
        q="rf survey",
        site="sds.crc.nd.edu",
        metadata_filters=[
            {
                "field_path": "capture_count",
                "query_type": "range",
                "filter_value": {"gte": 1},
            },
        ],
    )
    assert result["total"] == 0
    assert client.search_calls
    call = client.search_calls[0]
    assert call["index"] == "fed-datasets"
    must = call["body"]["query"]["bool"]["must"]
    assert {"term": {"is_federated_deleted": False}} in must
    assert {"term": {"site_name": "sds.crc.nd.edu"}} in must
    assert any("multi_match" in clause for clause in must)


@pytest.mark.regression
def test_load_federated_asset_returns_indexed_doc() -> None:
    opensearch = RecordingOpenSearch()
    site = "localhost"
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


@pytest.mark.regression
def test_load_federated_asset_missing_returns_none() -> None:
    opensearch = RecordingOpenSearch()
    assert (
        load_federated_asset(
            opensearch,
            site_name="localhost",
            uuid=TEST_DATASET_UUID,
            asset_type=AssetTypeEnum.DATASET,
        )
        is None
    )
