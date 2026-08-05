"""Helper functions for searching captures with metadata filtering."""

from collections.abc import Mapping
from typing import Any

from django.db.models import QuerySet
from loguru import logger as log
from opensearchpy import exceptions as os_exceptions
from rest_framework.request import Request
from rich.pretty import pretty_repr
from sds_opensearch_query import bool_must_search_body
from sds_opensearch_query import build_metadata_filter_clauses
from sds_opensearch_query import flatten_property_paths
from sds_opensearch_query import run_search
from sds_opensearch_query.query import DEFAULT_SEARCH_SIZE

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.capture_serializers import (
    build_composite_capture_data,
)
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.utils.asset_access_control import (
    get_accessible_captures_queryset,
)
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,
)
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.utils.relationship_utils import (
    group_captures_by_top_level_dir,
)
from sds_gateway.users.models import User

UNKNOWN_CAPTURE_TYPE = "Unknown capture type"

MAX_OS_SIZE = DEFAULT_SEARCH_SIZE


def _warn_unknown_field(field_path: str) -> None:
    msg = (
        f"Field '{field_path}' does not match an indexed field. "
        "The filter may not be applied to the query accurately."
    )
    log.warning(msg)


def _build_os_metadata_query(
    capture_type: CaptureType | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    known_paths = _known_field_paths_for_capture_type(capture_type)
    clauses = build_metadata_filter_clauses(
        metadata_filters,
        known_field_paths=known_paths,
        on_unknown_field=_warn_unknown_field,
    )
    log.debug(
        f"Built {len(clauses)} OpenSearch metadata queries: {clauses}",
    )
    return clauses


def _known_field_paths_for_capture_type(
    capture_type: CaptureType | None,
) -> frozenset[str]:
    implemented_capture_types = set(md_props_by_type.keys())
    assert implemented_capture_types, (
        "No capture types are implemented. Please check the metadata properties."
    )

    if capture_type is not None:
        if capture_type not in implemented_capture_types:
            msg = f"{UNKNOWN_CAPTURE_TYPE}: {capture_type}"
            raise ValueError(msg)
        properties = get_mapping_by_capture_type(capture_type)["properties"]
        return flatten_property_paths(properties)

    paths: set[str] = set()
    for ct in implemented_capture_types:
        properties = get_mapping_by_capture_type(ct)["properties"]
        paths.update(flatten_property_paths(properties))
    return frozenset(paths)


def get_capture_queryset(
    request_user: User,
    capture_type: CaptureType | None,
) -> QuerySet[Capture]:
    """Get the capture queryset based on the capture type."""
    capture_queryset = get_accessible_captures_queryset(request_user)

    if capture_type:
        if not md_props_by_type.get(capture_type):
            raise ValueError(UNKNOWN_CAPTURE_TYPE)
        capture_queryset = capture_queryset.filter(capture_type=capture_type)

    return capture_queryset.order_by("-updated_at")


def search_captures(
    request_user: User,
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
        request_user=request_user,
    )
    metadata_queries: list[dict[str, Any]] = _build_os_metadata_query(
        capture_type=capture_type,
        metadata_filters=metadata_filters,
    )
    if not metadata_queries:
        log.debug("No metadata queries provided. Returning all captures.")
        return capture_queryset

    must_clauses: list[dict[str, Any]] = []
    if capture_type:
        must_clauses.append({"term": {"capture_type": capture_type}})
    must_clauses.extend(metadata_queries)

    os_query = bool_must_search_body(*must_clauses)
    log.debug("OpenSearch query:")
    log.debug(pretty_repr(os_query, indent_size=4))

    client = get_opensearch_client()
    index_name: str = (
        "captures-*" if capture_type is None else infer_index_name(capture_type)
    )

    try:
        hits = run_search(
            client,
            index=index_name,
            body=os_query,
            size=MAX_OS_SIZE,
        )
    except os_exceptions.ConnectionError as err:
        msg = f"Failed to connect to OpenSearch: {err}"
        log.exception(msg)
        raise
    except ValueError as err:
        raise ValueError(str(err)) from err
    except os_exceptions.OpenSearchException as err:
        msg = f"OpenSearch generic error: {err}"
        log.exception(msg)
        raise

    capture_uuids: list[str] = [hit["_id"] for hit in hits]

    if not capture_uuids:
        log.debug("No captures found in OpenSearch.")
        return capture_queryset.none()

    num_hits = len(capture_uuids)
    if num_hits > 0.9 * MAX_OS_SIZE:
        log.warning(
            f"OpenSearch returned {num_hits:,} hits, which is close to the "
            f"maximum size of {MAX_OS_SIZE:,}. Consider refactoring.",
        )
    log.debug(f"Found {len(capture_uuids)} matching captures.")

    filtered_queryset = capture_queryset.filter(uuid__in=capture_uuids).order_by(
        "-updated_at",
    )

    log.debug(
        f"Found {len(capture_uuids)} captures in OpenSearch, "
        f"filtered to {filtered_queryset.count()} captures in database.",
    )

    return filtered_queryset


# TODO: add pagination before retrieval rather than after
# Need to paginate/limit OpenSearch results list before grouping
# and then paginate/limit the grouped captures
def get_composite_captures(
    captures: QuerySet[Capture],
    request: Request | None = None,
    bulk_metadata: dict[str, Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Get captures as composite objects, grouping multi-channel captures.

    Args:
        captures: QuerySet of Capture objects
        request: Optional Django REST framework request for serializer context
        bulk_metadata: Optional pre-loaded OpenSearch metadata mapping
                       ``uuid_str → metadata_dict``. When provided, the
                       serialization path populates related capture
                       instances' internal cache so ``get_opensearch_metadata()``
                       returns without additional round-trips.
    Returns:
        list: List of composite capture data
    """
    grouped_captures = group_captures_by_top_level_dir(captures)
    composite_captures = []

    context: dict[str, Any] = {"request": request} if request else {}
    if bulk_metadata is not None:
        context["bulk_metadata"] = bulk_metadata

    for capture_list in grouped_captures.values():
        if len(capture_list) > 1:
            composite_data = build_composite_capture_data(capture_list)
            composite_captures.append(composite_data)
        else:
            capture = capture_list[0]
            capture_data = serialize_capture_or_composite(capture, context=context)
            composite_captures.append(capture_data)

    return composite_captures
