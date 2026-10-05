"""Tests for federated OpenSearch list/search body construction."""

from __future__ import annotations

from unittest.mock import patch

from django.test import override_settings
from sds_opensearch_query.mapping import RFC_FED_CAPTURE_PROPERTIES

from sds_gateway.api_methods.federation.search_helpers import _build_fed_must_clauses
from sds_gateway.api_methods.federation.search_helpers import _build_fed_search_body
from sds_gateway.api_methods.helpers.list_helpers import _parse_freq_bounds_hz
from sds_gateway.api_methods.helpers.list_helpers import (
    federated_capture_list_metadata_filters,
)
from sds_gateway.api_methods.helpers.list_helpers import (
    federated_published_dataset_rows,
)
from sds_gateway.api_methods.helpers.list_helpers import merge_asset_list_rows
from sds_gateway.api_methods.helpers.list_helpers import serialize_peer_asset
from sds_gateway.api_methods.models import ItemType


def _site_name_must_not_clauses(body: dict) -> list[str]:
    must_not = body["query"]["bool"]["must_not"]
    sites: list[str] = []
    for clause in must_not:
        term = clause.get("term") or {}
        if "site_name" in term:
            sites.append(str(term["site_name"]))
    return sites


def _must_not_terms(body: dict) -> list[dict]:
    return body["query"]["bool"]["must_not"]


@override_settings(SDS_SITE_FQDN="local.example.com")
def test_fed_search_body_excludes_local_site_when_site_filter_unset() -> None:
    body = _build_fed_search_body(
        must=[{"term": {"is_deleted": False}}],
        site=None,
        for_datasets=True,
    )
    assert "local.example.com" in _site_name_must_not_clauses(body)


@override_settings(SDS_SITE_FQDN="local.example.com")
def test_fed_search_body_excludes_local_site_when_site_filter_is_local() -> None:
    body = _build_fed_search_body(
        must=[{"term": {"is_deleted": False}}],
        site="local.example.com",
        for_datasets=True,
    )
    must = body["query"]["bool"]["must"]
    assert {"term": {"site_name": "local.example.com"}} in must
    assert "local.example.com" in _site_name_must_not_clauses(body)


@override_settings(SDS_SITE_FQDN="local.example.com")
def test_fed_search_body_excludes_local_site_when_site_filter_is_peer() -> None:
    body = _build_fed_search_body(
        must=[{"term": {"is_deleted": False}}],
        site="peer.example.com",
        for_datasets=True,
    )
    must = body["query"]["bool"]["must"]
    assert {"term": {"site_name": "peer.example.com"}} in must
    assert "local.example.com" in _site_name_must_not_clauses(body)


def test_fed_dataset_search_body_excludes_non_public() -> None:
    body = _build_fed_search_body(must=[], site=None, for_datasets=True)
    assert {"is_public": False} in [c.get("term") for c in _must_not_terms(body)]


def test_fed_capture_search_body_requires_public_dataset_ids_not_is_public() -> None:
    body = _build_fed_search_body(must=[], site=None, for_datasets=False)
    must = body["query"]["bool"]["must"]
    assert {"exists": {"field": "public_dataset_ids"}} in must
    terms = [clause.get("term") for clause in _must_not_terms(body)]
    assert {"is_deleted": True} in terms
    assert not any("is_public" in (t or {}) for t in terms)


def test_federated_capture_list_metadata_filters_skips_default_freq_range() -> None:
    filters = federated_capture_list_metadata_filters(
        min_freq="0",
        max_freq="10",
    )
    assert filters == []


def test_federated_capture_list_metadata_filters_date_and_frequency() -> None:
    filters = federated_capture_list_metadata_filters(
        date_start="2024-01-01",
        date_end="2024-12-31",
        min_freq="1.0",
        max_freq="2.5",
    )
    assert filters[0] == {
        "field_path": "created_at",
        "query_type": "range",
        "filter_value": {
            "gte": "2024-01-01T00:00:00.000Z",
            "lte": "2024-12-31T23:59:59.999Z",
        },
    }
    assert filters[1]["field_path"] == "search_props.center_frequency"
    min_hz, max_hz = _parse_freq_bounds_hz("1.0", "2.5")
    assert filters[1]["filter_value"]["gte"] == min_hz
    assert filters[1]["filter_value"]["lte"] == max_hz


def test_build_fed_must_clauses_includes_capture_type_and_metadata() -> None:
    metadata = federated_capture_list_metadata_filters(date_start="2024-06-01")
    must = _build_fed_must_clauses(
        q=None,
        metadata_filters=metadata,
        rfc_properties=RFC_FED_CAPTURE_PROPERTIES,
        text_fields=["name"],
        extra_terms=[("capture_type", "digital-rf")],
    )
    terms = [clause.get("term") for clause in must if "term" in clause]
    assert {"capture_type": "digital-rf"} in terms
    ranges = [clause.get("range") for clause in must if "range" in clause]
    assert {"created_at": {"gte": "2024-06-01T00:00:00.000Z"}} in ranges


def test_serialize_peer_capture_sets_capture_type_display() -> None:
    row = serialize_peer_asset(
        {"uuid": "peer-cap", "capture_type": "drf"},
        ItemType.CAPTURE,
    )
    assert row["capture_type_display"] == "Digital RF"


@patch("sds_gateway.api_methods.helpers.list_helpers._get_peer_asset_rows")
def test_federated_published_dataset_rows_frequency_intersects_captures(
    mock_get_peer_rows,
) -> None:
    mock_get_peer_rows.side_effect = [
        [
            {"uuid": "ds-keep", "site_name": "peer.example", "name": "In band"},
            {"uuid": "ds-drop", "site_name": "peer.example", "name": "Out of band"},
        ],
        [
            {
                "uuid": "cap-1",
                "site_name": "peer.example",
                "public_dataset_ids": ["ds-keep"],
            },
        ],
    ]
    rows = federated_published_dataset_rows(
        min_freq="1.0",
        max_freq="2.0",
    )
    assert [row["uuid"] for row in rows] == ["ds-keep"]
    expected_peer_lookups = 2  # federated datasets, then federated captures (freq)
    assert mock_get_peer_rows.call_count == expected_peer_lookups
    capture_call = mock_get_peer_rows.call_args_list[1]
    assert capture_call.kwargs["asset_type"] == ItemType.CAPTURE
    assert capture_call.kwargs["query"] is None
    metadata = capture_call.kwargs["metadata_filters"]
    assert metadata
    assert metadata[0]["field_path"] == "search_props.center_frequency"


def test_merge_asset_list_rows_dedupes_by_uuid_prefers_local() -> None:
    local_rows = [
        {"uuid": "same-id", "name": "local", "is_federated": False},
    ]
    federated_rows = [
        {"uuid": "same-id", "name": "peer copy", "is_federated": True},
        {"uuid": "peer-only", "name": "peer", "is_federated": True},
    ]
    merged = merge_asset_list_rows(local_rows, federated_rows)
    uuids = [row["uuid"] for row in merged]
    assert uuids == ["same-id", "peer-only"]
    assert merged[0]["name"] == "local"
