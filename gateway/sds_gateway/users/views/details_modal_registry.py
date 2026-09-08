"""Registry for HTML details modal fragments (asset-type → builder)."""

from __future__ import annotations

import datetime as dt
import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from django.http import HttpRequest
from django.template.loader import render_to_string

from sds_opensearch_query.query import run_search

from sds_gateway.api_methods.federation.fed_index import FED_CAPTURES_INDEX
from sds_gateway.api_methods.federation.fed_index import FED_DATASETS_INDEX
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.serializers.dataset_serializers import get_dataset_serializer
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_capture
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_item
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client

TIME_METADATA_FIELDS = frozenset(
    {
        "computer_time",
        "start_bound",
        "end_bound",
        "init_utc_timestamp",
    },
)

FREQUENCY_METADATA_FIELDS = frozenset(
    {
        "center_frequency",
        "sample_rate",
        "bandwidth",
        "center_freq",
        "samples_per_second",
    },
)

# Frequency thresholds (Hz)
_FREQUENCY_GHZ_THRESHOLD = 1_000_000_000  # 1e9
_FREQUENCY_MHZ_THRESHOLD = 1_000_000  # 1e6


def _format_field_label(field_name: str) -> str:
    return field_name.replace("_", " ").title()


def _format_numeric_value(value: float, field_name: str = "") -> str | None:
    """Format a numeric metadata value for display.

    Formatting depends on field_name context rather than value heuristics:

    * Time fields (TIME_METADATA_FIELDS) → Unix epoch → date string
    * Frequency fields (FREQUENCY_METADATA_FIELDS) → Hz → GHz/MHz with units
    * Unknown fields → None (caller handles plain-number fallback)
    """
    if isinstance(value, bool):
        return "Yes" if value else "No"

    value_abs = abs(value)

    if field_name in TIME_METADATA_FIELDS:
        try:
            return datetime.fromtimestamp(value, tz=dt.UTC).strftime(
                "%Y-%m-%d %H:%M:%S %Z"
            )
        except (OSError, OverflowError, ValueError):
            return None

    if field_name in FREQUENCY_METADATA_FIELDS:
        if value_abs >= _FREQUENCY_GHZ_THRESHOLD:
            return f"{value / _FREQUENCY_GHZ_THRESHOLD:.3f} GHz"
        if value_abs >= _FREQUENCY_MHZ_THRESHOLD:
            return f"{value / _FREQUENCY_MHZ_THRESHOLD:.1f} MHz"

    return None


def _format_bool_or_str_text(value: object) -> str:
    """Format a boolean or string value to display text."""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str):
        lowered = value.lower()
        if lowered == "true":
            return "Yes"
        if lowered == "false":
            return "No"
        return value
    return str(value)


def _format_number_value(value: float, field_name: str) -> str:
    """Format a numeric value with proper separators or units."""
    numeric_result = _format_numeric_value(value, field_name)
    if numeric_result is not None:
        return numeric_result
    if isinstance(value, float) and value == value // 1:
        # Whole number → integer with thousand separators
        return f"{int(value):,}"
    return f"{value:,}"


def format_channel_metadata_value(value: Any, field_name: str = "") -> str:
    """Format a metadata value for display (parity with legacy ModalManager JS)."""
    if value is None:
        result = "N/A"
    elif isinstance(value, bool | str):
        result = _format_bool_or_str_text(value)
    elif isinstance(value, int | float):
        result = _format_number_value(value, field_name)
    elif isinstance(value, list):
        result = ", ".join(
            format_channel_metadata_value(item, field_name) for item in value
        )
    elif isinstance(value, dict):
        result = json.dumps(value, default=str)
    else:
        result = str(value)
    return result


def build_channel_metadata_rows(
    metadata: dict[str, Any] | None,
) -> list[dict[str, str]]:
    """Turn channel_metadata dict into rows for the template (autoescaped text)."""
    if not metadata:
        return []
    rows: list[dict[str, str]] = []
    for key, value in metadata.items():
        if value is None:
            continue
        rows.append(
            {
                "label": _format_field_label(str(key)),
                "value": format_channel_metadata_value(value, str(key)),
            }
        )
    return rows


def _owner_display(capture_dict: dict[str, Any]) -> str:
    owner = capture_dict.get("owner") or {}
    if isinstance(owner, dict):
        label = owner.get("email") or owner.get("name")
        if label:
            return str(label)
    owner_name = capture_dict.get("owner_name")
    if owner_name:
        return str(owner_name)
    return "N/A"


def _dataset_display(capture_dict: dict[str, Any]) -> str:
    datasets = capture_dict.get("datasets")
    if isinstance(datasets, list) and datasets:
        names = [
            str(d["name"]) for d in datasets if isinstance(d, dict) and d.get("name")
        ]
        return ", ".join(names) if names else "N/A"
    raw = capture_dict.get("dataset")
    if raw is not None and raw != "":
        return str(raw)
    return "N/A"


def _center_frequency_display(capture_dict: dict[str, Any]) -> str:
    raw = capture_dict.get("center_frequency_ghz")
    if raw is None or raw == "None":
        return "N/A"
    try:
        return f"{float(raw):.3f} GHz"
    except (TypeError, ValueError):
        return "N/A"


def _channel_summary_label(capture_dict: dict[str, Any]) -> str:
    return "Channels" if capture_dict.get("is_multi_channel") else "Channel"


def _channel_summary_value(capture_dict: dict[str, Any]) -> str:
    if capture_dict.get("is_multi_channel"):
        channels = capture_dict.get("channels") or []
        if isinstance(channels, list) and channels:
            parts = [
                str(ch["channel"])
                for ch in channels
                if isinstance(ch, dict) and ch.get("channel")
            ]
            return ", ".join(parts) if parts else "N/A"
        return str(capture_dict.get("channel") or "N/A")
    return str(capture_dict.get("channel") or "N/A")


def _accordion_channels(capture_dict: dict[str, Any]) -> list[dict[str, Any]]:
    """Channels with precomputed metadata rows for accordion."""
    if not capture_dict.get("is_multi_channel"):
        return []
    channels = capture_dict.get("channels") or []
    if not isinstance(channels, list):
        return []
    out: list[dict[str, Any]] = []
    for ch in channels:
        if not isinstance(ch, dict):
            continue
        meta = ch.get("channel_metadata") or {}
        meta_rows = build_channel_metadata_rows(meta if isinstance(meta, dict) else {})
        out.append(
            {
                "channel_name": str(ch.get("channel") or "N/A"),
                "metadata_rows": meta_rows,
            }
        )
    return out


def _capture_file_summary_from_dict(capture_dict: dict[str, Any]) -> tuple[int, int]:
    """Read file count and total size from serialized capture (no file list)."""
    files_count = capture_dict.get("total_file_count")
    if files_count is None:
        info = capture_dict.get("data_files_info")
        if isinstance(info, dict) and ("total_count" in info or "count" in info):
            files_count = info.get("total_count", info.get("count"))
    if files_count is None:
        files_count = capture_dict.get("file_count")

    total_size = capture_dict.get("total_file_size")
    if total_size is None:
        info = capture_dict.get("data_files_info")
        if isinstance(info, dict) and "total_size" in info:
            total_size = info.get("total_size")
    if total_size is None:
        total_size = capture_dict.get("size")

    return int(files_count or 0), int(total_size or 0)


def _run_search_for_fed_asset(index: str, body: dict[str, Any]) -> dict[str, Any] | None:
    client = get_opensearch_client()
    hits = run_search(
        client=client,
        index=index,
        body=body,
        size=1,
    )
    if not hits:
        return None
    return hits[0].get("_source") or None


def build_capture_details_modal_context(
    request: HttpRequest,
    capture_uuid: UUID,
    federated_peer: bool = False,
) -> dict[str, Any] | None:
    """
    Build template context for capture details modal body.

    Returns None if capture not found or user cannot access it.
    """
    try:
        if federated_peer:
            body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"uuid": str(capture_uuid)}},
                            {"term": {"is_deleted": False}},
                            {"exists": {"field": "public_dataset_ids"}},
                        ],
                    },
                },
            }
            capture_dict = _run_search_for_fed_asset(FED_CAPTURES_INDEX, body)
            if capture_dict is None:
                return None
        else:
            if not request.user.is_authenticated:
                return None

            capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)
            
            if not user_has_access_to_capture(request.user, capture):
                return None

            capture_dict = serialize_capture_or_composite(
                capture,
                context={"request": request, "exclude_files": True},
            )
    except Capture.DoesNotExist:
        return None

    uuid_str = str(capture_dict.get("uuid", capture_uuid))

    files_count, total_size = _capture_file_summary_from_dict(capture_dict)

    return {
        "capture": capture_dict,
        "capture_uuid": uuid_str,
        "owner_display": _owner_display(capture_dict),
        "center_frequency_display": _center_frequency_display(capture_dict),
        "channel_label": _channel_summary_label(capture_dict),
        "channel_value": _channel_summary_value(capture_dict),
        "accordion_channels": _accordion_channels(capture_dict),
        "is_public_yesno": "Yes" if capture_dict.get("is_public") or federated_peer else "No",
        "dataset_display": _dataset_display(capture_dict),
        "files_count": files_count,
        "total_size": total_size,
    }


def capture_details_title(capture_dict: dict[str, Any]) -> str:
    name = capture_dict.get("name") or ""
    top = capture_dict.get("top_level_dir") or ""
    if name:
        return str(name)
    if top:
        return str(top)
    return "Unnamed Capture"


def capture_details_meta(capture_dict: dict[str, Any]) -> dict[str, Any]:
    """JSON meta for ModalManager (visualize, etc.)."""
    ct = capture_dict.get("capture_type") or ""
    return {
        "visualize_enabled": ct == "drf",
        "capture_type": str(ct),
        "uuid": str(capture_dict.get("uuid", "")),
        "name": str(capture_dict.get("name") or ""),
        "top_level_dir": str(capture_dict.get("top_level_dir") or ""),
    }


def finalize_capture_modal_json(ctx: dict[str, Any], html: str) -> dict[str, Any]:
    cap = ctx["capture"]
    return {
        "html": html,
        "title": capture_details_title(cap),
        "meta": capture_details_meta(cap),
    }


def load_dataset_details_bundle(
    request: HttpRequest,
    dataset_uuid: UUID,
    federated_peer: bool = False,
) -> dict[str, Any] | None:
    """
    Build dataset details payload (dataset dict and file statistics).

    Returns None if the dataset does not exist or is not visible to the request user.
    On success, includes ``dataset_orm`` for server-rendered templates (omit from JSON).
    """
    try:
        if federated_peer:
            body = {
                "query": {
                    "bool": {
                        "must": [
                            {"term": {"uuid": str(dataset_uuid)}},
                            {"term": {"is_deleted": False}},
                            {"term": {"is_public": True}},
                        ],
                    },
                },
            }
            dataset_data = _run_search_for_fed_asset(FED_DATASETS_INDEX, body)
            if dataset_data is None:
                return None
            capture_file_count = dataset_data.get("capture_file_count", 0)
            artifact_file_count = dataset_data.get("artifact_file_count", 0)
            total_size = dataset_data.get("size", 0)
            statistics = {
                "total_files": capture_file_count + artifact_file_count,
                "captures": capture_file_count,
                "artifacts": artifact_file_count,
                "total_size": total_size,
            }
            updated_at = dataset_data.get("updated_at", None)
        else:
            dataset = Dataset.objects.get(uuid=dataset_uuid, is_deleted=False)
            
            has_public_access = dataset.is_public and dataset.status == DatasetStatus.FINAL
            has_user_access = request.user.is_authenticated and user_has_access_to_item(
                request.user, dataset_uuid, ItemType.DATASET
            )

            if not (has_public_access or has_user_access):
                return None
            
            serializer_context: dict[str, Any] = {"exclude_files": True}
            if request.user.is_authenticated:
                serializer_context["request"] = request

            dataset_data = get_dataset_serializer(
                dataset,
                has_user_access=has_user_access,
                context=serializer_context,
            )
            statistics = dataset.get_dataset_file_statistics()
            updated_at = dataset.updated_at
    except Dataset.DoesNotExist:
        return None

    return {
        "dataset": dataset_data,
        "statistics": statistics,
        "updated_at": updated_at,
    }


def build_dataset_details_modal_context(
    request: HttpRequest, dataset_uuid: UUID, federated_peer: bool = False,
) -> dict[str, Any] | None:
    bundle = load_dataset_details_bundle(
        request,
        dataset_uuid,
        federated_peer=federated_peer,
    )
    if bundle is None:
        return None

    ds = bundle["dataset"]
    uuid_str = str(ds.get("uuid", dataset_uuid))

    return {
        "dataset": ds,
        "statistics": bundle["statistics"],
        "dataset_updated_at": bundle["updated_at"],
        "dataset_uuid": uuid_str,
    }


def finalize_dataset_modal_json(ctx: dict[str, Any], html: str) -> dict[str, Any]:
    ds = ctx["dataset"]
    name = str(ds.get("name") or "Dataset")
    ver = ds.get("version")
    title = f"{name} (v{ver})" if ver is not None else name
    return {
        "html": html,
        "title": title,
        "meta": {"uuid": str(ds.get("uuid", ""))},
    }


def render_details_modal_body(
    request: HttpRequest, asset_type: str, ctx: dict[str, Any]
) -> str:
    template_name = DETAILS_MODAL_BODY_TEMPLATES.get(asset_type)
    if not template_name:
        return ""
    return render_to_string(template_name, ctx, request=request)


def get_registered_asset_types() -> frozenset[str]:
    return frozenset(DETAILS_MODAL_REGISTRY.keys())


DetailsModalContextBuilder = Callable[..., dict[str, Any] | None]
DetailsModalJsonBuilder = Callable[[dict[str, Any], str], dict[str, Any]]

DETAILS_MODAL_REGISTRY: dict[str, DetailsModalContextBuilder] = {
    "capture": build_capture_details_modal_context,
    "dataset": build_dataset_details_modal_context,
}

DETAILS_MODAL_BODY_TEMPLATES: dict[str, str] = {
    "capture": "users/components/capture_details_modal_body.html",
    "dataset": "users/components/dataset_details_modal_body.html",
}

DETAILS_MODAL_JSON_BUILDERS: dict[str, DetailsModalJsonBuilder] = {
    "capture": finalize_capture_modal_json,
    "dataset": finalize_dataset_modal_json,
}

CAPTURE_FILES_SUMMARY_TEMPLATE = "users/components/capture_files_summary_fragment.html"
