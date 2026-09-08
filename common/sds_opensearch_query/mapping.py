from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

if TYPE_CHECKING:
    from collections.abc import Mapping

FED_INDEX_SETTINGS: dict[str, Any] = {
    "index": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
}

# RFC §6 — fed-datasets search fields (aligned with FederatedDatasetDoc / export)
RFC_FED_DATASET_PROPERTIES: dict[str, dict[str, Any]] = {
    "uuid": {"type": "keyword"},
    "site_name": {"type": "keyword"},  # peer FQDN (federation.toml [site].fqdn)
    "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
    "description": {"type": "text"},
    "abstract": {"type": "text"},
    "keywords": {"type": "keyword"},
    "owner_name": {"type": "keyword"},
    "status": {"type": "keyword"},
    "is_public": {"type": "boolean"},
    "is_deleted": {"type": "boolean"},
    "created_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "updated_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "federation_event_at": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis",
    },
    "size": {"type": "long"},
    "capture_count": {"type": "integer"},
    "capture_file_count": {"type": "integer"},
    "artifact_file_count": {"type": "integer"},
    "url": {"type": "keyword"},
}

# fed-captures: identity fields plus local capture OpenSearch prop dicts
# To see the full list of capture props and search props, see:
#   gateway/sds_gateway/api_methods/utils/metadata_schemas.py
RFC_FED_CAPTURE_PROPERTIES: dict[str, dict[str, Any]] = {
    "uuid": {"type": "keyword"},
    "site_name": {"type": "keyword"},  # peer FQDN (federation.toml [site].fqdn)
    "name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
    "capture_type": {"type": "keyword"},
    "channel": {"type": "keyword"},
    "scan_group": {"type": "keyword"},
    "top_level_dir": {"type": "keyword"},
    "owner_name": {"type": "keyword"},
    "file_count": {"type": "integer"},
    "size": {"type": "long"},
    "created_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "updated_at": {"type": "date", "format": "strict_date_optional_time||epoch_millis"},
    "federation_event_at": {
        "type": "date",
        "format": "strict_date_optional_time||epoch_millis",
    },
    "is_deleted": {"type": "boolean"},
    "capture_props": {"type": "nested", "dynamic": True},
    "search_props": {"type": "nested", "dynamic": True},
    "public_dataset_ids": {"type": "keyword"},
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


def flatten_property_paths(
    properties: Mapping[str, Any],
    *,
    prefix: str = "",
    separator: str = ".",
) -> frozenset[str]:
    """Collect dotted field paths from an OpenSearch ``properties`` mapping."""
    paths: set[str] = set()

    for field, spec in properties.items():
        path = f"{prefix}{separator}{field}" if prefix else field
        if not isinstance(spec, dict):
            paths.add(path)
            continue

        if spec.get("type") == "nested":
            nested_props = spec.get("properties", {})
            if isinstance(nested_props, dict):
                for nested_field in nested_props:
                    paths.add(f"{path}{separator}{nested_field}")
            continue

        if "properties" in spec:
            paths.update(
                flatten_property_paths(
                    spec["properties"],
                    prefix=path,
                    separator=separator,
                ),
            )
            continue

        paths.add(path)

    return frozenset(paths)
