"""OpenSearch index definitions for federated metadata (RFC fed-datasets / fed-captures).

Explicit ``properties`` match the RFC search-facing field lists; export-only and
envelope fields (e.g. ``status``, ``capture_props``, ``is_federated_deleted``) rely on
dynamic mapping.
"""

from __future__ import annotations

from typing import Any

from sds_federation.schemas.webhooks import AssetTypeEnum

FED_INDEX_SETTINGS: dict[str, Any] = {
    "index": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}

# RFC §6 — fed-datasets search fields
RFC_FED_DATASET_PROPERTIES: dict[str, dict[str, Any]] = {
    "uuid": {"type": "keyword"},
    "site_name": {"type": "keyword"},  # peer FQDN (federation.toml [site].fqdn)
    "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
    "description": {"type": "text"},
    "abstract": {"type": "text"},
    "keywords": {"type": "keyword"},
    "owner_name": {"type": "keyword"},
    "created_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "updated_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "size": {"type": "long"},
    "capture_count": {"type": "integer"},
    "url": {"type": "keyword"},
}

# RFC §6 — fed-captures search fields
RFC_FED_CAPTURE_PROPERTIES: dict[str, dict[str, Any]] = {
    "uuid": {"type": "keyword"},
    "site_name": {"type": "keyword"},  # peer FQDN (federation.toml [site].fqdn)
    "capture_type": {"type": "keyword"},
    "channel": {"type": "keyword"},
    "center_frequency": {"type": "double"},
    "sample_rate": {"type": "double"},
    "start_time": {"type": "long"},
    "end_time": {"type": "long"},
    "dataset_ids": {"type": "keyword"},
    "url": {"type": "keyword"},
}


def _fed_mappings(properties: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {
        "dynamic": True,
        "properties": properties,
    }


def fed_dataset_mappings() -> dict[str, Any]:
    return _fed_mappings(RFC_FED_DATASET_PROPERTIES)


def fed_capture_mappings() -> dict[str, Any]:
    return _fed_mappings(RFC_FED_CAPTURE_PROPERTIES)


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
