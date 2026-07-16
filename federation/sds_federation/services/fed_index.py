from __future__ import annotations

import asyncio
from typing import Any
from datetime import datetime
from uuid import UUID

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError

from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import asset_doc_class
from sds_federation.schemas.opensearch_indices import index_body_for_asset


def ensure_fed_indices(client: OpenSearch) -> None:
    for asset_type in AssetTypeEnum:
        index_name = asset_type.index_name
        if client.indices.exists(index=index_name):
            continue
        client.indices.create(
            index=index_name,
            body=index_body_for_asset(asset_type),
        )


def doc_id(site_name: str, uuid: UUID) -> str:
    return f"{site_name}:{uuid}"


def _parse_event_at(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        return datetime.fromisoformat(value)
    return None


_FEDERATION_META_KEYS = frozenset({"federation_event_at"})


def _strip_federation_meta(source: dict) -> dict:
    return {
        key: value for key, value in source.items() if key not in _FEDERATION_META_KEYS
    }



_LIST_PAGE_SIZE = 1000


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




def _site_owned_query(site_name: str) -> dict[str, Any]:
    return {
        "bool": {
            "should": [
                {"term": {"site_name.keyword": site_name}},
                {"term": {"site_name": site_name}},
            ],
            "minimum_should_match": 1,
        }
    }


def list_federated_assets_for_site(
    client: OpenSearch,
    *,
    site_name: str,
    asset_type: AssetTypeEnum,
) -> list[FederatedDatasetDoc | FederatedCaptureDoc]:
    """Return all fed-* docs owned by ``site_name`` (paginated search_after)."""
    docs: list[FederatedDatasetDoc | FederatedCaptureDoc] = []
    search_after: list[Any] | None = None

    while True:
        body: dict[str, Any] = {
            "size": _LIST_PAGE_SIZE,
            "sort": [{"_id": "asc"}],
            "query": _site_owned_query(site_name),
        }
        if search_after is not None:
            body["search_after"] = search_after

        response = client.search(index=asset_type.index_name, body=body)
        hits = (response.get("hits") or {}).get("hits") or []
        if not hits:
            break

        for hit in hits:
            source = hit.get("_source")
            if not isinstance(source, dict):
                continue
            if source.get("site_name") != site_name:
                continue
            parsed = _parse_hit(source, asset_type)
            if parsed is not None:
                docs.append(parsed)

        if len(hits) < _LIST_PAGE_SIZE:
            break
        last_sort = hits[-1].get("sort")
        if not isinstance(last_sort, list) or not last_sort:
            break
        search_after = last_sort

    return docs


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


class FederatedAssetIndexer:
    def __init__(self, client: OpenSearch) -> None:
        self._client = client
        # Process-local cache; OpenSearch federation_event_at is authoritative.
        self._last_event: dict[str, datetime] = {}

    def _stored_event_at(self, index_name: str, _id: str) -> datetime | None:
        try:
            doc = self._client.get(index=index_name, id=_id)
        except NotFoundError:
            return None
        source = doc.get("_source") or {}
        return _parse_event_at(source.get("federation_event_at"))

    def _is_stale(
        self,
        site_name: str,
        uuid: UUID,
        event_at: datetime,
        *,
        index_name: str,
    ) -> bool:
        key = doc_id(site_name, uuid)
        prev = self._last_event.get(key)
        if prev is None:
            prev = self._stored_event_at(index_name, key)
            if prev is not None:
                self._last_event[key] = prev
        return bool(prev is not None and event_at <= prev)

    def _mark_applied(self, site_name: str, uuid: UUID, event_at: datetime) -> None:
        self._last_event[doc_id(site_name, uuid)] = event_at

    def apply_asset_event(
        self,
        *,
        event_at: datetime,
        site_name: str,
        asset: FederatedDatasetDoc | FederatedCaptureDoc | None,
        asset_type: AssetTypeEnum,
    ) -> bool:
        if asset is None:
            kind = asset_type.value
            msg = f"{kind} body required for {kind}-updated webhook"
            raise ValueError(msg)

        if asset.site_name != site_name:
            raise ValueError(f"site_name must match {asset_type.value}.site_name")

        if self._is_stale(
            site_name,
            asset.uuid,
            event_at,
            index_name=asset_type.index_name,
        ):
            return False

        _id = doc_id(site_name, asset.uuid)
        body = asset.model_dump(mode="json")
        body["federation_event_at"] = event_at.isoformat()
        self._client.index(
            index=asset_type.index_name,
            id=_id,
            body=body,
            refresh="wait_for",
        )

        self._mark_applied(site_name, asset.uuid, event_at)
        return True
