"""Lightweight serializers shared across capture and dataset graphs.

This module must not import ``capture_serializers`` or ``dataset_serializers`` at
load time so those modules can depend on summaries without circular imports.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.utils.relationship_utils import get_dataset_captures
from sds_gateway.api_methods.utils.relationship_utils import (
    group_captures_by_top_level_dir,
)


class DatasetSummarySerializer(serializers.ModelSerializer[Dataset]):
    """Minimal dataset shape for capture ``datasets`` (breaks serializer cycles)."""

    class Meta:
        model = Dataset
        fields = ["uuid", "name", "version", "status", "is_public"]


class CaptureSummarySerializer(serializers.ModelSerializer[Capture]):
    """Minimal capture shape for dataset ``captures`` (single-channel row)."""

    is_multi_channel = serializers.SerializerMethodField()
    channels = serializers.SerializerMethodField()

    class Meta:
        model = Capture
        fields = [
            "uuid",
            "capture_type",
            "top_level_dir",
            "index_name",
            "origin",
            "is_multi_channel",
            "channels",
        ]

    def get_is_multi_channel(self, _obj: Capture) -> bool:
        return False

    def get_channels(self, obj: Capture) -> list[dict[str, Any]]:
        return [{"channel": obj.channel, "uuid": obj.uuid}]


def composite_capture_summary(captures: list[Capture]) -> dict[str, Any]:
    """
    Stripped multi-channel row: same keys as CaptureSummarySerializer.

    Args:
        captures: List of Capture objects
    Returns:
        dict: Composite capture summary
    """
    if not captures:
        msg = "No captures provided for composite summary"
        raise ValueError(msg)
    base = captures[0]
    return {
        "uuid": base.uuid,
        "capture_type": base.capture_type,
        "top_level_dir": base.top_level_dir,
        "index_name": base.index_name,
        "origin": base.origin,
        "is_multi_channel": True,
        "channels": [{"channel": c.channel, "uuid": c.uuid} for c in captures],
    }


def serialize_captures_for_dataset_detail(
    dataset: Dataset,
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One summary row per logical capture (no full capture or composite payloads)."""
    non_deleted_captures = get_dataset_captures(
        dataset,
        include_deleted=False,
    )
    grouped = group_captures_by_top_level_dir(non_deleted_captures)
    rows: list[dict[str, Any]] = []
    for capture_list in grouped.values():
        if len(capture_list) > 1:
            rows.append(composite_capture_summary(capture_list))
        else:
            rows.append(
                CaptureSummarySerializer(
                    capture_list[0],
                    context=context,
                ).data
            )
    return rows
