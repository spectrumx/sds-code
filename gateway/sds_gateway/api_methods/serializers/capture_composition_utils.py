"""Capture composition utilities for the SDS Gateway API methods."""

from typing import Any

from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.capture_serializers import (
    CompositeCaptureSerializer,
)
from sds_gateway.api_methods.serializers.user_serializer import UserGetSerializer


def build_composite_capture_data(
    captures: list[Capture],
    *,
    include_serializer_aux: bool = False,
) -> dict[str, Any]:
    """Build composite capture data from a list of captures with the same top_level_dir.

    Args:
        captures: List of Capture objects to combine into composite
        include_serializer_aux: When True, attach non-public fields used only by
            :class:`CompositeCaptureSerializer`: per-channel cached OpenSearch
            metadata (one search per capture) and a Capture map to avoid duplicate
            ORM lookups. Keep False for raw API payloads (capture list/search,
            nested dataset captures).

    Returns:
        dict: Composite capture data structure

    Raises:
        ValueError: If no captures are provided
    """
    if not captures:
        error_msg = "No captures provided for composite"
        raise ValueError(error_msg)

    # Use the first capture as the base for common fields
    base_capture = captures[0]

    # Build channel data with metadata
    captures_by_uuid: dict[str, Capture] | None = {} if include_serializer_aux else None
    channels: list[dict[str, Any]] = []
    for capture in captures:
        if captures_by_uuid is not None:
            captures_by_uuid[str(capture.uuid)] = capture
        channel_data: dict[str, Any] = {
            "channel": capture.channel,
            "uuid": capture.uuid,
            "channel_metadata": retrieve_indexed_metadata(capture),
        }
        if include_serializer_aux:
            channel_data["_per_channel_os_meta"] = capture.get_opensearch_metadata()
        channels.append(channel_data)

    # Serialize the owner field
    owner_serializer = UserGetSerializer(base_capture.owner)

    # Build composite data
    composite: dict[str, Any] = {
        "uuid": base_capture.uuid,  # Use first capture's UUID as composite UUID
        "capture_type": base_capture.capture_type,
        "capture_type_display": base_capture.get_capture_type_display(),
        "top_level_dir": base_capture.top_level_dir,
        "index_name": base_capture.index_name,
        "origin": base_capture.origin,
        "is_multi_channel": True,
        "created_at": base_capture.created_at,
        "updated_at": base_capture.updated_at,
        "deleted_at": base_capture.deleted_at,
        "is_deleted": base_capture.is_deleted,
        "is_public": base_capture.is_public,
        "owner": owner_serializer.data,
        "channels": channels,
    }
    if captures_by_uuid is not None:
        composite["_captures_by_uuid"] = captures_by_uuid
    return composite


def serialize_capture_or_composite(
    capture: Capture, context: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Serialize a capture as single or composite based on multi-channel status.

    Args:
        capture: Capture object to serialize
        context: Optional context for serialization

    Returns:
        dict: Serialized capture data
    """
    capture_data = capture.get_capture()

    if capture_data["is_composite"]:
        # Serialize as composite
        composite_data = build_composite_capture_data(
            capture_data["captures"],
            include_serializer_aux=True,
        )
        serializer = CompositeCaptureSerializer(composite_data, context=context)
        return serializer.data
    # Serialize as single capture
    serializer = CaptureGetSerializer(capture_data["capture"], context=context)
    return serializer.data
