"""Read and search federated documents in shared fed-* OpenSearch indices."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from opensearchpy import OpenSearch
from opensearchpy.exceptions import NotFoundError
from sds_opensearch_query import bool_must_search_body
from sds_opensearch_query import build_metadata_filter_clauses
from sds_opensearch_query import federation_not_deleted_clause
from sds_opensearch_query import flatten_property_paths
from sds_opensearch_query import multi_match_clause
from sds_opensearch_query import run_search
from sds_opensearch_query import term_clause
from sds_opensearch_query.query import DEFAULT_SEARCH_SIZE

from sds_federation.schemas.opensearch_indices import RFC_FED_CAPTURE_PROPERTIES
from sds_federation.schemas.opensearch_indices import RFC_FED_DATASET_PROPERTIES
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.schemas.webhooks import asset_doc_class
from sds_federation.services.fed_index import doc_id

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

FED_DATASET_TEXT_FIELDS = [
    "name^2",
    "description",
    "abstract",
    "keywords",
    "owner_name",
]

FED_CAPTURE_TEXT_FIELDS = [
    "name",
    "channel",
    "capture_type",
]

_WILDCARD_SITES = frozenset({"", "*", "all"})


def _site_clause(site: str | None) -> dict[str, Any] | None:
    if site is None or site.strip().lower() in _WILDCARD_SITES:
        return None
    return term_clause("site_name", site.strip())


def _text_clause(q: str | None, fields: list[str]) -> dict[str, Any] | None:
    if q is None or not q.strip():
        return None
    return multi_match_clause(q.strip(), fields)


def _hits_to_response(hits: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(hits),
        "hits": [
            {
                "id": hit["_id"],
                "score": hit.get("_score"),
                "source": hit.get("_source", {}),
            }
            for hit in hits
        ],
    }


def _build_fed_must_clauses(
    *,
    q: str | None,
    site: str | None,
    metadata_filters: list[dict[str, Any]] | None,
    rfc_properties: Mapping[str, dict[str, Any]],
    text_fields: list[str],
    extra_terms: list[tuple[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    known = flatten_property_paths(rfc_properties)
    must: list[dict[str, Any]] = [federation_not_deleted_clause()]

    site_filter = _site_clause(site)
    if site_filter is not None:
        must.append(site_filter)

    for field, value in extra_terms or ():
        if value is not None and value != "":
            must.append(term_clause(field, value))

    text = _text_clause(q, text_fields)
    if text is not None:
        must.append(text)

    must.extend(
        build_metadata_filter_clauses(
            metadata_filters,
            known_field_paths=known,
        ),
    )
    return must


def search_federated_datasets(
    client: OpenSearch,
    *,
    q: str | None = None,
    site: str | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
    size: int = DEFAULT_SEARCH_SIZE,
) -> dict[str, Any]:
    must = _build_fed_must_clauses(
        q=q,
        site=site,
        metadata_filters=metadata_filters,
        rfc_properties=RFC_FED_DATASET_PROPERTIES,
        text_fields=FED_DATASET_TEXT_FIELDS,
    )
    body = bool_must_search_body(*must)
    hits = run_search(
        client,
        index=AssetTypeEnum.DATASET.index_name,
        body=body,
        size=size,
    )
    return _hits_to_response(hits)


def search_federated_captures(
    client: OpenSearch,
    *,
    q: str | None = None,
    site: str | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
    capture_type: str | None = None,
    size: int = DEFAULT_SEARCH_SIZE,
) -> dict[str, Any]:
    must = _build_fed_must_clauses(
        q=q,
        site=site,
        metadata_filters=metadata_filters,
        rfc_properties=RFC_FED_CAPTURE_PROPERTIES,
        text_fields=FED_CAPTURE_TEXT_FIELDS,
        extra_terms=[("capture_type", capture_type)],
    )
    body = bool_must_search_body(*must)
    hits = run_search(
        client,
        index=AssetTypeEnum.CAPTURE.index_name,
        body=body,
        size=size,
    )
    return _hits_to_response(hits)
