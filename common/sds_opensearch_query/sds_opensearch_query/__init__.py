"""Framework-agnostic OpenSearch query helpers."""

from sds_opensearch_query.filters import build_metadata_filter_clauses
from sds_opensearch_query.filters import nested_query_clause
from sds_opensearch_query.mapping import flatten_property_paths
from sds_opensearch_query.query import bool_must_search_body
from sds_opensearch_query.query import federation_not_deleted_clause
from sds_opensearch_query.query import multi_match_clause
from sds_opensearch_query.query import run_search
from sds_opensearch_query.query import term_clause

__all__ = [
    "bool_must_search_body",
    "build_metadata_filter_clauses",
    "federation_not_deleted_clause",
    "flatten_property_paths",
    "multi_match_clause",
    "nested_query_clause",
    "run_search",
    "term_clause",
]
