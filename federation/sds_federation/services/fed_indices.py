"""Create fed-datasets / fed-captures OpenSearch indices if missing."""

from __future__ import annotations

from opensearchpy import OpenSearch

from sds_federation.schemas.opensearch_indices import index_body_for_asset
from sds_federation.schemas.webhooks import AssetTypeEnum


def ensure_fed_indices(client: OpenSearch) -> None:
    for asset_type in AssetTypeEnum:
        index_name = asset_type.index_name
        if client.indices.exists(index=index_name):
            continue
        client.indices.create(
            index=index_name,
            body=index_body_for_asset(asset_type),
        )
