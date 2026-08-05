"""Framework-agnostic OpenSearch query helpers."""

from sds_opensearch_query.filters import build_metadata_filter_clauses
from sds_opensearch_query.filters import nested_query_clause
from sds_opensearch_query.index_write import FED_CAPTURES_INDEX
from sds_opensearch_query.index_write import FED_DATASETS_INDEX
from sds_opensearch_query.index_write import federated_doc_id
from sds_opensearch_query.index_write import index_federated_document
from sds_opensearch_query.mapping import flatten_property_paths
from sds_opensearch_query.query import bool_must_search_body
from sds_opensearch_query.query import federation_not_deleted_clause
from sds_opensearch_query.query import multi_match_clause
from sds_opensearch_query.query import run_search
from sds_opensearch_query.query import term_clause
from sds_opensearch_query.redis_channel import FEDERATION_EVENTS_CHANNEL_PREFIX
from sds_opensearch_query.redis_channel import federation_events_channel
from sds_opensearch_query.redis_channel import resolve_federation_events_channel

__all__ = [
    "FEDERATION_EVENTS_CHANNEL_PREFIX",
    "FED_CAPTURES_INDEX",
    "FED_DATASETS_INDEX",
    "bool_must_search_body",
    "build_metadata_filter_clauses",
    "federated_doc_id",
    "federation_events_channel",
    "federation_not_deleted_clause",
    "flatten_property_paths",
    "index_federated_document",
    "multi_match_clause",
    "nested_query_clause",
    "resolve_federation_events_channel",
    "run_search",
    "term_clause",
]
