"""Read federated documents from shared fed-* OpenSearch indices."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from opensearchpy.exceptions import NotFoundError

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import asset_doc_class
from sds_federation.services.fed_index import doc_id

if TYPE_CHECKING:
    from uuid import UUID

    from opensearchpy import OpenSearch

_FEDERATION_META_KEYS = frozenset({"federation_event_at"})
_LIST_PAGE_SIZE = 1000


def _strip_federation_meta(source: dict) -> dict:
    return {
        key: value for key, value in source.items() if key not in _FEDERATION_META_KEYS
    }


def _parse_hit(
    source: dict,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    if not isinstance(source, dict):
        return None
    doc_class = asset_doc_class(asset_type)
    return doc_class.model_validate(_strip_federation_meta(source))


def load_federated_asset(
    client: OpenSearch,
    *,
    site_name: str,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    """Return the indexed document for a site asset, or None if missing."""

    def _get() -> dict | None:
        try:
            response = client.get(
                index=asset_type.index_name, id=doc_id(site_name, uuid)
            )
        except NotFoundError:
            return None
        source = response.get("_source")
        if not isinstance(source, dict):
            return None
        return source

    source = _get()
    if source is None:
        return None
    return _parse_hit(source, asset_type)


def list_federated_assets_for_site(
    client: OpenSearch,
    *,
    site_name: str,
    asset_type: AssetTypeEnum,
) -> list[FederatedDatasetDoc | FederatedCaptureDoc]:
    """Return all fed-* docs owned by ``site_name`` (for peer sync export)."""
    body = {
        "size": _LIST_PAGE_SIZE,
        "query": {
            "bool": {
                "should": [
                    {"term": {"site_name.keyword": site_name}},
                    {"term": {"site_name": site_name}},
                ],
                "minimum_should_match": 1,
            }
        },
    }
    response = client.search(index=asset_type.index_name, body=body)
    hits = (response.get("hits") or {}).get("hits") or []
    docs: list[FederatedDatasetDoc | FederatedCaptureDoc] = []
    for hit in hits:
        source = hit.get("_source")
        if not isinstance(source, dict):
            continue
        if source.get("site_name") != site_name:
            continue
        parsed = _parse_hit(source, asset_type)
        if parsed is not None:
            docs.append(parsed)
    return docs


async def aload_federated_asset(
    client: OpenSearch,
    *,
    site_name: str,
    uuid: UUID,
    asset_type: AssetTypeEnum,
) -> FederatedDatasetDoc | FederatedCaptureDoc | None:
    return await asyncio.to_thread(
        load_federated_asset,
        client,
        site_name=site_name,
        uuid=uuid,
        asset_type=asset_type,
    )


async def alist_federated_assets_for_site(
    client: OpenSearch,
    *,
    site_name: str,
    asset_type: AssetTypeEnum,
) -> list[FederatedDatasetDoc | FederatedCaptureDoc]:
    return await asyncio.to_thread(
        list_federated_assets_for_site,
        client,
        site_name=site_name,
        asset_type=asset_type,
    )
