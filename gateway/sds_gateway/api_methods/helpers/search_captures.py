"""Helper functions for searching captures with metadata filtering."""

import logging
from typing import Any

from django.db.models import QuerySet
from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import base_index_fields
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,  # type: dict[CaptureType, dict[str, Any]]
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import User

logger = logging.getLogger(__name__)

RangeValue = dict[str, int | float]
UNKNOWN_CAPTURE_TYPE = "Unknown capture type"


def build_metadata_query(
    capture_type: CaptureType | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build OpenSearch query for metadata fields.

    Args:
        capture_type: Type of capture (e.g. 'drf')
        metadata_filters: list of dicts with 'field', 'type', and 'value' keys

    Returns:
        List of OpenSearch query clauses for the metadata fields
    """

    if not capture_type:
        # if no capture type is provided, return all fields from all capture types
        index_mapping = {
            capture_type: md_props_by_type[capture_type] for capture_type in CaptureType
        }
    else:
        index_mapping = md_props_by_type.get(capture_type, {})

    # flatten the index mapping to list of fields
    index_fields = base_index_fields.copy()  # Start with a copy of base fields
    for field, field_type in index_mapping.items():
        if isinstance(field_type, dict) and field_type.get("type") == "nested":
            for nested_field in field_type.get("properties", {}):
                index_fields.append(f"capture_props.{field}.{nested_field}")
        else:
            index_fields.append(f"capture_props.{field}")

    # Build metadata query
    metadata_queries = []
    for query in metadata_filters:
        field_path = query["field"]

        # warn if the field is not in the index mapping
        # but continue to build the query
        if field_path not in index_fields:
            msg = (
                f"Field '{field_path}' does not match an indexed field."
                "The filter may not be applied to the query accurately."
            )
            logger.warning(msg)

        metadata_queries.append({query["type"]: {field_path: query["value"]}})

    return metadata_queries


def search_captures(
    user: User,
    capture_type: CaptureType | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
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

    index_name = "captures-*" if capture_type is None else f"captures-{capture_type}"

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
