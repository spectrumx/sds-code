"""OpenSearch index definitions for federated metadata (RFC fed-* indices).

Explicit ``properties`` match the RFC search-facing field lists; export-only and
envelope fields (e.g. ``status``, ``capture_props``, ``is_deleted``) rely on
dynamic mapping.
"""

from __future__ import annotations

from typing import Any

from sds_opensearch_query.mapping import FED_INDEX_SETTINGS
from sds_opensearch_query.mapping import fed_capture_mappings
from sds_opensearch_query.mapping import fed_dataset_mappings

from sds_federation.schemas.webhooks import AssetTypeEnum


def index_body_for_asset(asset_type: AssetTypeEnum) -> dict[str, Any]:
    mappings = (
        fed_dataset_mappings()
        if asset_type == AssetTypeEnum.DATASET
        else fed_capture_mappings()
    )
    return {
        "settings": FED_INDEX_SETTINGS,
        "mappings": mappings,
    }


def index_body_for_index_name(index_name: str) -> dict[str, Any]:
    if index_name == AssetTypeEnum.DATASET.index_name:
        return index_body_for_asset(AssetTypeEnum.DATASET)
    if index_name == AssetTypeEnum.CAPTURE.index_name:
        return index_body_for_asset(AssetTypeEnum.CAPTURE)
    msg = f"unknown federated index: {index_name}"
    raise ValueError(msg)
