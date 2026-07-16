"""Gateway-side OpenSearch search against shared fed-* indices."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from opensearchpy import OpenSearch
from sds_opensearch_query import bool_must_search_body
from sds_opensearch_query import build_metadata_filter_clauses
from sds_opensearch_query import federation_not_deleted_clause
from sds_opensearch_query import flatten_property_paths
from sds_opensearch_query import multi_match_clause
from sds_opensearch_query import run_search
from sds_opensearch_query import term_clause
from sds_opensearch_query.mapping import RFC_FED_CAPTURE_PROPERTIES
from sds_opensearch_query.mapping import RFC_FED_DATASET_PROPERTIES
from sds_opensearch_query.query import DEFAULT_SEARCH_SIZE

from sds_gateway.api_methods.federation.fed_index import FED_CAPTURES_INDEX
from sds_gateway.api_methods.federation.fed_index import FED_DATASETS_INDEX

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
        index=FED_DATASETS_INDEX,
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
        index=FED_CAPTURES_INDEX,
        body=body,
        size=size,
    )
    return _hits_to_response(hits)
