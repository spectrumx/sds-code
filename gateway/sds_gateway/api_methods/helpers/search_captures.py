"""Helper functions for searching captures with metadata filtering."""

import logging
from typing import Any

from django.db.models import QuerySet
from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import User

logger = logging.getLogger(__name__)

RangeValue = dict[str, int | float]
UNKNOWN_CAPTURE_TYPE = "Unknown capture type"


def build_metadata_query(
    capture_type: str,
    metadata_filters: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build OpenSearch query for metadata fields.

    Args:
        capture_type: Type of capture (e.g. 'drf')
        metadata_filters: Dictionary of metadata field names and their filter values.
            For range queries on supported fields, value should be a dict with
            'gte'/'lte' keys.
            Example: {"center_freq": {"gte": 1000000, "lte": 2000000}}

    Returns:
        List of OpenSearch query clauses for the metadata fields
    """
    index_mapping = md_props_by_type.get(capture_type, {})

    # Build metadata query
    metadata_queries = []
    for field, value in metadata_filters.items():
        # Skip if field is not in index mapping
        if field not in index_mapping:
            continue

        field_path = f"metadata.{field}"

        # Handle range queries for supported fields
        if isinstance(value, dict):
            range_query: RangeValue = {}
            if "gte" in value:
                range_query["gte"] = value["gte"]
            if "lte" in value:
                range_query["lte"] = value["lte"]
            if range_query:
                metadata_queries.append({"range": {field_path: range_query}})
        else:
            # Regular exact match query
            metadata_queries.append({"match": {field_path: value}})

    return metadata_queries


def search_captures(
    user: User,
    capture_type: CaptureType | None = None,
    metadata_filters: dict[str, Any] | None = None,
) -> QuerySet[Capture]:
    """Search for captures with optional metadata filtering.

    Args:
        user: User to filter captures by ownership (required)
        capture_type: Optional type of capture to filter by (e.g. 'drf')
        metadata_filters: Optional dict of metadata field names and their filter values

    Returns:
        QuerySet of Capture objects matching the criteria

    Raises:
        ValueError: If the capture type is invalid
    """

    # Start with base queryset filtered by user
    # Start with base queryset filtered by user and not deleted
    captures = Capture.objects.filter(owner=user, is_deleted=False)

    # Filter by capture type if provided
    if capture_type:
        # Verify capture type exists before filtering
        if not md_props_by_type.get(capture_type):
            raise ValueError(UNKNOWN_CAPTURE_TYPE)
        captures = captures.filter(capture_type=capture_type)

    # If no metadata filters, return all matching captures
    if not metadata_filters or not capture_type:
        return captures

    # Build metadata query
    metadata_queries = build_metadata_query(capture_type, metadata_filters)
    if not metadata_queries:
        return captures

    # Build the full query with both capture_type and metadata filters
    query = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"capture_type": capture_type}},
                    *metadata_queries,
                ],
            },
        },
    }

    # Search OpenSearch
    client = get_opensearch_client()
    index_name = f"captures-{capture_type}"

    try:
        response = client.search(
            index=index_name,
            body=query,
        )
        # Get UUIDs of matching documents
        matching_uuids = [hit["_id"] for hit in response["hits"]["hits"]]
        # Filter captures by matching UUIDs
        return captures.filter(uuid__in=matching_uuids)
    except os_exceptions.NotFoundError as err:
        # Log the error
        msg = f"Index '{index_name}' not found"
        logger.exception(msg)
        raise ValueError(msg) from err
    except os_exceptions.ConnectionError as e:
        # Log the error
        msg = f"Failed to connect to OpenSearch: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
    except os_exceptions.RequestError as e:
        # Log the error
        msg = f"OpenSearch query error: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
    except os_exceptions.OpenSearchException as e:
        # Log the error
        msg = f"OpenSearch error: {e}"
        logger.exception(msg)
        # Handle the error (e.g., retry, raise an exception, etc.)
        raise
