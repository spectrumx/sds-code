"""Regression tests for shared sds_opensearch_query package."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from sds_opensearch_query import bool_must_search_body
from sds_opensearch_query import build_metadata_filter_clauses
from sds_opensearch_query import nested_query_clause
from sds_opensearch_query.client import build_opensearch_client

pytest.importorskip("sds_opensearch_query")


@pytest.mark.regression
def test_nested_query_clause_single_level() -> None:
    clause = nested_query_clause(
        field_path="center_frequency",
        query_type="term",
        value=1.0,
        levels_nested=0,
        last_path="search_props",
    )
    assert clause == {"term": {"search_props.center_frequency": 1.0}}


@pytest.mark.regression
def test_build_metadata_filter_clauses_term_and_nested() -> None:
    clauses = build_metadata_filter_clauses(
        [
            {
                "field_path": "capture_type",
                "query_type": "term",
                "filter_value": "digital-rf",
            },
            {
                "field_path": "search_props.center_frequency",
                "query_type": "range",
                "filter_value": {"gte": 100},
            },
        ],
    )
    assert len(clauses) == 2
    assert clauses[0] == {"term": {"capture_type": "digital-rf"}}
    assert "nested" in clauses[1]


@pytest.mark.regression
def test_bool_must_search_body() -> None:
    body = bool_must_search_body({"term": {"site_name": "crc"}})
    assert body["query"]["bool"]["must"] == [{"term": {"site_name": "crc"}}]


@pytest.mark.regression
def test_build_opensearch_client_omits_http_auth_when_user_blank() -> None:
    with patch("sds_opensearch_query.client.OpenSearch") as mock_os:
        build_opensearch_client(host="opensearch", port=9200, user="", password="")
    kwargs = mock_os.call_args.kwargs
    assert "http_auth" not in kwargs


@pytest.mark.regression
def test_build_opensearch_client_sets_http_auth_when_user_set() -> None:
    with patch("sds_opensearch_query.client.OpenSearch") as mock_os:
        build_opensearch_client(
            host="opensearch",
            port=9200,
            user="admin",
            password="secret",
        )
    auth = mock_os.call_args.kwargs["http_auth"]
    assert auth.username == "admin"
    assert auth.password == "secret"
