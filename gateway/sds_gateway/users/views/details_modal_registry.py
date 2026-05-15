"""Registry for HTML details modal fragments (asset-type → builder)."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from django.http import HttpRequest
from django.template.defaultfilters import filesizeformat
from django.template.loader import render_to_string
from django.utils import timezone

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_capture
from sds_gateway.users.views.datasets import load_dataset_details_bundle

TIME_METADATA_FIELDS = frozenset(
    {
        "computer_time",
        "start_bound",
        "end_bound",
        "init_utc_timestamp",
    },
)


def _format_field_label(field_name: str) -> str:
    return field_name.replace("_", " ").title()


def format_channel_metadata_value(value: Any, field_name: str = "") -> str:
    """Format a metadata value for display (parity with legacy ModalManager JS)."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, str):
        low = value.lower()
        if low == "true":
            return "Yes"
        if low == "false":
            return "No"
        return value
    if isinstance(value, int | float):
        value_str = str(value)
        fname = field_name.lower()
        if fname in TIME_METADATA_FIELDS and 10 <= len(value_str) <= 13:
            ts_ms = value * 1000 if len(value_str) == 10 else value
            try:
                return datetime.fromtimestamp(
                    ts_ms / 1000.0,
                    tz=timezone.utc,
                ).strftime("%Y-%m-%d %H:%M:%S %Z")
            except (OSError, OverflowError, ValueError):
                pass
        abs_v = abs(value)
        if abs_v >= 1e9:
            return f"{value / 1e9:.3f} GHz"
        if abs_v >= 1e6:
            return f"{value / 1e6:.1f} MHz"
        return str(value)
    if isinstance(value, list):
        return ", ".join(
            format_channel_metadata_value(item, field_name) for item in value
        )
    if isinstance(value, dict):
        return json.dumps(value, default=str)
    return str(value)


def build_channel_metadata_rows(metadata: dict[str, Any] | None) -> list[dict[str, str]]:
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
        return str(owner.get("email") or owner.get("name") or "N/A")
    return "N/A"


def _dataset_display(capture_dict: dict[str, Any]) -> str:
    datasets = capture_dict.get("datasets")
    if isinstance(datasets, list) and datasets:
        names: list[str] = []
        for d in datasets:
            if isinstance(d, dict) and d.get("name"):
                names.append(str(d["name"]))
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
            parts = []
            for ch in channels:
                if isinstance(ch, dict) and ch.get("channel"):
                    parts.append(str(ch["channel"]))
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


def build_capture_details_modal_context(
    request: HttpRequest, capture_uuid: UUID
) -> dict[str, Any] | None:
    """
    Build template context for capture details modal body.

    Returns None if capture not found or user cannot access it.
    """
    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)
    except Capture.DoesNotExist:
        return None

    if not request.user.is_authenticated:
        return None

    if not user_has_access_to_capture(request.user, capture):
        return None

    capture_dict = serialize_capture_or_composite(
        capture, context={"request": request}
    )
    uuid_str = str(capture_dict.get("uuid", capture_uuid))

    return {
        "capture": capture_dict,
        "capture_uuid": uuid_str,
        "owner_display": _owner_display(capture_dict),
        "center_frequency_display": _center_frequency_display(capture_dict),
        "channel_label": _channel_summary_label(capture_dict),
        "channel_value": _channel_summary_value(capture_dict),
        "accordion_channels": _accordion_channels(capture_dict),
        "is_public_yesno": "Yes" if capture_dict.get("is_public") else "No",
        "dataset_display": _dataset_display(capture_dict),
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


def build_capture_files_summary_context(
    request: HttpRequest, capture_uuid: UUID
) -> dict[str, Any] | None:
    base = build_capture_details_modal_context(request, capture_uuid)
    if base is None:
        return None
    cap = base["capture"]
    files = cap.get("files") or []
    files_count = len(files) if isinstance(files, list) else 0
    total_size = cap.get("total_file_size")
    if total_size is None:
        total_size = 0
    return {
        "files_count": files_count,
        "total_size": int(total_size) if total_size is not None else 0,
    }


def _format_tree_size_for_modal(n: Any) -> str:
    try:
        b = int(n)
    except (TypeError, ValueError):
        b = 0
    return str(filesizeformat(b))


def _format_tree_timestamp_for_modal(value: Any) -> str:
    if value is None:
        return "Unknown"
    if hasattr(value, "strftime"):
        dt = value
        if timezone.is_naive(dt):
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        dt = timezone.localtime(dt)
        return dt.strftime("%b %d, %Y, %I:%M %p").replace(" 0", " ")
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return _format_tree_timestamp_for_modal(parsed)
        except ValueError:
            return value
    return str(value)


def flatten_dataset_tree_to_modal_rows(
    node: dict[str, Any] | None,
    depth: int = 0,
) -> list[dict[str, Any]]:
    """Flatten FileTreeMixin tree to rows for users/components/modal_file_tree.html."""
    if node is None:
        return []
    rows: list[dict[str, Any]] = []

    files = node.get("files") or []
    if isinstance(files, list):
        for file in files:
            if not isinstance(file, dict):
                continue
            rows.append(
                {
                    "indent_level": depth,
                    "indent_range": list(range(depth)),
                    "icon": "bi-file-earmark",
                    "icon_color": "text-primary",
                    "name": str(file.get("name") or ""),
                    "type": str(file.get("media_type") or file.get("type") or "File"),
                    "size": _format_tree_size_for_modal(file.get("size")),
                    "created_at": _format_tree_timestamp_for_modal(file.get("created_at")),
                    "has_chevron": False,
                }
            )

    children = node.get("children") or {}
    if not isinstance(children, dict):
        return rows

    for child_node in children.values():
        if not isinstance(child_node, dict):
            continue
        if child_node.get("type") != "directory":
            continue
        name = str(child_node.get("name") or "")
        rows.append(
            {
                "indent_level": depth,
                "indent_range": list(range(depth)),
                "icon": "bi-folder",
                "icon_color": "text-warning",
                "name": f"{name}/" if name else "/",
                "type": "Directory",
                "size": _format_tree_size_for_modal(child_node.get("size")),
                "created_at": _format_tree_timestamp_for_modal(
                    child_node.get("created_at")
                ),
                "has_chevron": True,
            }
        )
        rows.extend(
            flatten_dataset_tree_to_modal_rows(child_node, depth + 1),
        )

    return rows


def build_dataset_details_modal_context(
    request: HttpRequest, dataset_uuid: UUID
) -> dict[str, Any] | None:
    bundle = load_dataset_details_bundle(request, dataset_uuid)
    if bundle is None:
        return None

    dataset_orm = bundle["dataset_orm"]
    tree_rows = flatten_dataset_tree_to_modal_rows(bundle.get("tree"))
    ds = bundle["dataset"]
    uuid_str = str(ds.get("uuid", dataset_uuid))

    return {
        "dataset": ds,
        "statistics": bundle["statistics"],
        "tree_rows": tree_rows,
        "dataset_updated_at": dataset_orm.updated_at,
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


DetailsModalContextBuilder = Callable[[HttpRequest, UUID], dict[str, Any] | None]
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
