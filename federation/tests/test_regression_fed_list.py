"""Regression tests for federated asset list/export helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta
from typing import TYPE_CHECKING
from uuid import uuid4

import pytest
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.bootstrap import _index_export_docs
from sds_federation.services.bootstrap import _parse_doc_event_at
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_search import _LIST_PAGE_SIZE
from sds_federation.services.fed_search import list_federated_assets_for_site
from sds_federation.testing.sample_data import sample_federated_dataset_doc

from tests.support.federation_mesh import peer_one_config

if TYPE_CHECKING:
    from tests.support.mock_opensearch import RecordingOpenSearch


@pytest.mark.regression
def test_list_federated_assets_paginates_past_page_size(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    indexer = FederatedAssetIndexer(recording_opensearch)
    site_name = "testsite"
    total = _LIST_PAGE_SIZE + 25
    for _ in range(total):
        doc = sample_federated_dataset_doc(uuid=uuid4(), site_name=site_name)
        indexer.apply_asset_event(
            event_at=datetime(2026, 1, 1, tzinfo=UTC),
            site_name=site_name,
            asset=doc,
            asset_type=AssetTypeEnum.DATASET,
        )

    listed = list_federated_assets_for_site(
        recording_opensearch,
        site_name=site_name,
        asset_type=AssetTypeEnum.DATASET,
    )
    assert len(listed) == total
    assert len(recording_opensearch.search_calls) >= 2


@pytest.mark.regression
def test_parse_doc_event_at_prefers_updated_at() -> None:
    updated = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    fallback = updated + timedelta(days=1)
    doc = sample_federated_dataset_doc().model_copy(
        update={"updated_at": updated.isoformat()},
    )
    assert _parse_doc_event_at(doc, fallback=fallback) == updated


@pytest.mark.regression
def test_bootstrap_index_uses_doc_updated_at_not_shared_now(
    recording_opensearch: RecordingOpenSearch,
) -> None:
    updated = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    shared_now = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
    doc = sample_federated_dataset_doc(site_name="testsite").model_copy(
        update={"updated_at": updated.isoformat()},
    )
    peer = peer_one_config().peers[0].model_copy(update={"name": "testsite"})
    indexer = FederatedAssetIndexer(recording_opensearch)

    count = _index_export_docs(
        indexer,
        peer,
        AssetTypeEnum.DATASET,
        [doc],
        fallback_event_at=shared_now,
    )

    assert count == 1
    assert (
        recording_opensearch.index_calls[0]["body"]["federation_event_at"]
        == updated.isoformat()
    )

    # A later webhook with the asset's updated_at must not look stale.
    assert (
        indexer.apply_asset_event(
            event_at=updated + timedelta(seconds=1),
            site_name="testsite",
            asset=doc.model_copy(update={"name": "newer"}),
            asset_type=AssetTypeEnum.DATASET,
        )
        is True
    )
