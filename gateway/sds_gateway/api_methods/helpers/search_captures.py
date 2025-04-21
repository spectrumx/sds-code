"""Helper functions for searching captures with metadata filtering."""

from collections.abc import Mapping
from typing import Any

from django.db.models import QuerySet
from loguru import logger as log
from opensearchpy import exceptions as os_exceptions
from rich.pretty import pretty_repr

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import base_index_fields
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,  # type: dict[CaptureType, dict[str, Any]]
)
from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.users.models import User

RangeValue = dict[str, int | float]
UNKNOWN_CAPTURE_TYPE = "Unknown capture type"


def handle_nested_query(
    field_path: str,
    query_type: str,
    value: Any,
    levels_nested: int,
    last_path: str | None = None,
) -> dict[str, Any]:
    """Build a nested metadata query for a given field path and value.

    Args:
        field_path: Full path to the field (e.g.'capture_props.metadata.fmax')
        query_type: Type of query (e.g. 'match', 'term')
        value: Value to match against
        levels_nested: Number of nested levels to traverse
    Returns:
        Nested query dictionary for OpenSearch
    """

    if levels_nested == 0:
        return {query_type: {f"{last_path}.{field_path}": value}}

    path_parts = field_path.split(".")
    current_path = path_parts[0]
    if last_path is not None:
        current_path = f"{last_path}.{current_path}"

    return {
        "nested": {
            "path": current_path,
            "query": handle_nested_query(
                field_path=".".join(path_parts[1:]),
                query_type=query_type,
                value=value,
                levels_nested=levels_nested - 1,
                last_path=current_path,
            ),
        },
    }


def _build_os_metadata_query(
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

    metadata_queries: list[dict[str, Any]] = []
    if metadata_filters is None:
        log.debug("No metadata filters provided to build the OpenSearch query.")
        return metadata_queries

    index_fields = _flatten_index_mapping(
        index_mapping=_get_index_mapping(capture_type=capture_type),
        index_fields=base_index_fields.copy(),
    )

    for query in metadata_filters:
        field_path: str = query["field_path"]
        query_type: str = query["query_type"]
        filter_value: Any = query["filter_value"]

        # warn if the field is not in the index mapping
        # but continue to build the query
        if field_path not in index_fields:
            msg = (
                f"Field '{field_path}' does not match an indexed field."
                "The filter may not be applied to the query accurately."
            )
            log.warning(msg)

        levels_nested = field_path.count(".")
        if levels_nested > 0:
            metadata_queries.append(
                handle_nested_query(
                    field_path=field_path,
                    query_type=query_type,
                    value=filter_value,
                    levels_nested=levels_nested,
                ),
            )
        else:
            metadata_queries.append({query_type: {field_path: filter_value}})

    log.debug(
        f"Built {len(metadata_queries)} OpenSearch metadata "
        f"queries: {metadata_queries}",
    )
    return metadata_queries


def _flatten_index_mapping(
    index_mapping: Mapping[str, Any],
    index_fields: list[str],
    prefix: str = "capture_props",
    separator: str = ".",
) -> list[str]:
    """Flatten the index mapping to a list of fields.
    Args:
        index_mapping: The index mapping to flatten.
        index_fields: The list of fields to flatten.
    Returns:
        A list of flattened fields.
    """
    for field, field_type in index_mapping.items():
        if isinstance(field_type, dict) and field_type.get("type") == "nested":
            index_fields.extend(
                [
                    f"{prefix}{separator}{field}{separator}{nested_field}"
                    for nested_field in field_type.get("properties", {})
                ],
            )
        else:
            index_fields.append(f"{prefix}{separator}{field}")
    return index_fields


def _get_index_mapping(capture_type: CaptureType | None) -> dict[str, dict[str, Any]]:
    """Retrieves the OpenSearch index mapping for a given capture type or all types.

    Args:
        capture_type: The capture type for which the index mapping is requested.
                      If None, the function merges all capture type properties.
    Raises:
        ValueError: If the capture type is not None and is not recognized.
    Returns:
        A dict where the keys are property names and the values are dicts with
        metadata for the specified capture type or all capture types combined.
    """
    implemented_capture_types = set(md_props_by_type.keys())
    assert implemented_capture_types, (
        "No capture types are implemented. Please check the metadata properties."
    )

    if capture_type is not None:
        if capture_type not in implemented_capture_types:
            msg = f"{UNKNOWN_CAPTURE_TYPE}: {capture_type}"
            raise ValueError(msg)
        index_mapping = md_props_by_type.get(capture_type, {})
    else:
        # merge all capture type properties into a single flat dictionary
        index_mapping = {}
        for ct in implemented_capture_types:
            index_mapping.update(md_props_by_type[ct])
    return index_mapping


def get_capture_queryset(
    owner: User,
    capture_type: CaptureType | None,
) -> QuerySet[Capture]:
    """Get the capture queryset based on the capture type."""
    # start with base queryset filtered by user and not deleted
    capture_queryset = Capture.objects.filter(owner=owner, is_deleted=False)

    # filter by capture type if provided
    if capture_type:
        # verify capture type exists before filtering
        if not md_props_by_type.get(capture_type):
            raise ValueError(UNKNOWN_CAPTURE_TYPE)
        capture_queryset = capture_queryset.filter(capture_type=capture_type)

    return capture_queryset.order_by("-updated_at")


def search_captures(
    owner: User,
    capture_type: CaptureType | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> QuerySet[Capture]:
    """Search for captures with optional metadata filtering.

    Args:
        owner:              user who owns the captures
        capture_type:       type of capture to filter by
        metadata_filters:   dict of metadata field names and their filter values
    Raises:
        ValueError:         when the index was not found
    Returns:
        QuerySet of Capture objects matching the criteria
    """

    capture_queryset: QuerySet[Capture] = get_capture_queryset(
        capture_type=capture_type,
        owner=owner,
    )
    metadata_queries: list[dict[str, Any]] = _build_os_metadata_query(
        capture_type=capture_type,
        metadata_filters=metadata_filters,
    )
    if not metadata_queries:
        log.debug("No metadata queries provided. Returning all captures.")
        return capture_queryset

    os_query = _build_os_query_for_captures(
        capture_type=capture_type,
        metadata_queries=metadata_queries,
    )

    client = get_opensearch_client()
    index_name: str = (
        "captures-*" if capture_type is None else infer_index_name(capture_type)
    )

    try:
        response = client.search(
            index=index_name,
            body=os_query,
        )
    except os_exceptions.NotFoundError as err:
        msg = f"Index '{index_name}' not found"
        log.exception(msg)
        raise ValueError(msg) from err
    except os_exceptions.ConnectionError as err:
        msg = f"Failed to connect to OpenSearch: {err}"
        log.exception(msg)
        raise
    except os_exceptions.RequestError as err:
        msg = f"OpenSearch request error: {err}"
        log.exception(msg)
        raise
    except os_exceptions.OpenSearchException as err:
        msg = f"OpenSearch generic error: {err}"
        log.exception(msg)
        raise
    else:
        matching_uuids = [hit["_id"] for hit in response["hits"]["hits"]]
        return capture_queryset.filter(uuid__in=matching_uuids).order_by("-updated_at")


def _build_os_query_for_captures(
    capture_type: CaptureType | None,
    metadata_queries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build the OpenSearch query for searching captures.

    Args:
        capture_type:       The type of capture to filter by, or None for all types.
        metadata_queries:   A list of metadata query clauses to include in the query.

    Returns:
        A dictionary representing the OpenSearch query.
    """
    must_clauses: list[dict[str, dict[str, Any]]] = []
    if capture_type:
        must_clauses.append({"term": {"capture_type": capture_type}})
    must_clauses.extend(metadata_queries)

    query = {
        "query": {
            "bool": {
                "must": must_clauses,
            },
        },
    }
    log.debug("OpenSearch query:")
    log.debug(pretty_repr(query, indent_size=4))
    return query
