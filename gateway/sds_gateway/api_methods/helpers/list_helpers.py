"""Lightweight list-row adapters for local and federated asset UI lists."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils import dateparse
from django.utils import timezone

from sds_gateway.api_methods.federation.availability import is_federation_operational
from sds_gateway.api_methods.federation.search_helpers import search_federated_captures
from sds_gateway.api_methods.federation.search_helpers import search_federated_datasets
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client

log = logging.getLogger(__name__)

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet

    from sds_gateway.users.models import User


BASE_ASSET_DICT = {
    "is_federated": False,
    "is_owner": False,
    "is_shared": False,
    "is_shared_with_me": False,
    "permission_level": None,
    "dropdown_menu_items": [],
}


def local_site_name() -> str:
    """FQDN used as ``site_name`` for local rows (RFC peer identity)."""
    return str(getattr(settings, "SDS_SITE_FQDN", "") or "").strip()


def _parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed: datetime | None = value
    elif isinstance(value, str):
        parsed = dateparse.parse_datetime(value)
    else:
        return None
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _capture_display_name(row: dict[str, Any]) -> str:
    return (
        str(row.get("name") or "").strip()
        or str(row.get("top_level_dir") or "").strip()
        or "Capture"
    )


def asset_list_dropdown_menu_items(
    row: dict[str, Any],
    *,
    asset_type: ItemType,
) -> list[dict[str, Any]]:
    """Build dropdown_menu.html items for a capture or dataset list row."""
    uuid = str(row.get("uuid") or "")
    if not uuid:
        return []

    is_owner = bool(row.get("is_owner"))
    permission_level = row.get("permission_level")
    is_contributor = permission_level == PermissionLevel.CONTRIBUTOR
    is_co_owner = permission_level == PermissionLevel.CO_OWNER

    if asset_type == ItemType.CAPTURE:
        return _capture_list_dropdown_menu_items(
            uuid=uuid,
            row=row,
            is_owner=is_owner,
            is_contributor=is_contributor,
            is_co_owner=is_co_owner,
        )

    return _dataset_list_dropdown_menu_items(
        uuid=uuid,
        row=row,
        is_owner=is_owner,
        is_contributor=is_contributor,
        is_co_owner=is_co_owner,
    )


def dataset_list_dropdown_menu_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    if row.get("is_federated"):
        return []
    return asset_list_dropdown_menu_items(row, asset_type=ItemType.DATASET)


def capture_list_dropdown_menu_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    return asset_list_dropdown_menu_items(row, asset_type=ItemType.CAPTURE)


def _capture_list_dropdown_menu_items(
    *,
    uuid: str,
    row: dict[str, Any],
    is_owner: bool,
    is_contributor: bool,
    is_co_owner: bool,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    if is_owner:
        display_name = _capture_display_name(row)
        items.append(
            {
                "label": "Add to dataset",
                "icon": "folder-plus",
                "type": "button",
                "extra_class": "add-to-dataset-btn",
                "data_attrs": {
                    "capture-uuid": uuid,
                    "capture-name": display_name[:200],
                },
            }
        )
        top_level = str(row.get("top_level_dir") or "").strip()
        items.append(
            {
                "label": "Reindex",
                "icon": "arrow-repeat",
                "type": "button",
                "extra_class": "reindex-capture-btn",
                "data_attrs": {
                    "capture-uuid": uuid,
                    "capture-name": display_name[:200],
                    "top-level-dir": top_level[:500],
                },
            }
        )
        items.append(
            {
                "label": "Delete",
                "icon": "trash",
                "type": "button",
                "extra_class": "delete-asset-btn",
                "data_attrs": {
                    "asset-type": "capture",
                    "asset-uuid": uuid,
                    "asset-name": display_name[:200],
                    **({"asset-shared": "true"} if row.get("is_shared") else {}),
                },
            }
        )

    if is_owner or is_contributor or is_co_owner:
        items.append(
            {
                "label": "Share",
                "icon": "person-plus",
                "type": "button",
                "modal_toggle": True,
                "modal_target": f"#shareModal-{uuid}",
                "data_attrs": {},
            }
        )

    items.append(
        {
            "label": "Download",
            "icon": "download",
            "type": "button",
            "modal_toggle": True,
            "modal_target": f"#webDownloadModal-{uuid}",
            "data_attrs": {},
        }
    )
    return items


def _dataset_list_dropdown_menu_items(
    *,
    uuid: str,
    row: dict[str, Any],
    is_owner: bool,
    is_contributor: bool,
    is_co_owner: bool,
) -> list[dict[str, Any]]:
    dataset_published = row.get("status") == DatasetStatus.FINAL and row.get(
        "is_public"
    )

    items: list[dict[str, Any]] = []
    if is_owner or is_contributor or is_co_owner:
        items.append(
            {
                "label": "Share",
                "icon": "person-plus",
                "type": "button",
                "modal_toggle": True,
                "modal_target": f"#shareModal-{uuid}",
                "data_attrs": {},
            }
        )

        if not dataset_published:
            items.append(
                {
                    "label": "Edit",
                    "icon": "pencil",
                    "type": "link",
                    "href": f"{reverse('users:group_captures')}?dataset_uuid={uuid}",
                    "data_attrs": {},
                }
            )

    if is_owner or is_co_owner:
        items.append(
            {
                "label": "Create New Version",
                "icon": "folder-symlink",
                "type": "button",
                "modal_toggle": True,
                "modal_target": f"#versioningModal-{uuid}",
                "data_attrs": {},
            }
        )
        if not dataset_published:
            items.append(
                {
                    "label": "Publish",
                    "icon": "globe",
                    "type": "button",
                    "modal_toggle": True,
                    "modal_target": f"#publish-dataset-modal-{uuid}",
                    "data_attrs": {"dataset-uuid": uuid},
                    "extra_class": "publish-dataset-btn",
                }
            )

    status = row.get("status")
    is_public = bool(row.get("is_public"))
    is_deletable_dataset = status == DatasetStatus.DRAFT and not is_public
    if is_owner and is_deletable_dataset:
        dataset_name = str(row.get("name") or "").strip() or "Dataset"
        items.append(
            {
                "label": "Delete",
                "icon": "trash",
                "type": "button",
                "extra_class": "delete-asset-btn",
                "data_attrs": {
                    "asset-type": ItemType.DATASET,
                    "asset-uuid": uuid,
                    "asset-name": dataset_name[:200],
                    **({"asset-shared": "true"} if row.get("is_shared") else {}),
                },
            }
        )

    items.append(
        {
            "label": "Web Download",
            "icon": "download",
            "type": "button",
            "modal_toggle": True,
            "modal_target": f"#webDownloadModal-{uuid}",
            "data_attrs": {},
        }
    )
    items.append(
        {
            "label": "SDK Instructions",
            "icon": "code-slash",
            "type": "button",
            "modal_toggle": True,
            "modal_target": f"#sdkDownloadModal-{uuid}",
            "data_attrs": {},
        }
    )
    return items


def _keyword_names(dataset: Dataset) -> list[str]:
    return [
        kw.name for kw in dataset.keywords.all() if not getattr(kw, "is_deleted", False)
    ]


_LIST_ROW_DATETIME_FIELDS = frozenset({"created_at", "updated_at"})

# ORM / OpenSearch field names populated on list rows (beyond BASE_ASSET_DICT).
_DATASET_LIST_FIELDS: tuple[str, ...] = (
    "uuid",
    "name",
    "version",
    "authors",
    "keywords",
    "created_at",
    "updated_at",
    "is_public",
    "status",
    "status_display",
    "owner_name",
    "site_name",
    "abstract",
    "description",
)

_CAPTURE_LOCAL_FIELD_DEFAULTS: dict[str, Any] = {
    "capture_props": {},
    "search_props": {},
    "file_count": 0,
    "size": 0,
}

_CAPTURE_TYPE_DISPLAY: dict[str, str] = dict(Capture.CAPTURE_TYPE_CHOICES)


def _capture_type_display(capture_type: Any) -> str:
    key = str(capture_type or "").strip()
    return _CAPTURE_TYPE_DISPLAY.get(key, key)


_CAPTURE_LIST_FIELDS: tuple[str, ...] = (
    "uuid",
    "name",
    "top_level_dir",
    "capture_type",
    "capture_type_display",
    "channel",
    "scan_group",
    "file_count",
    "size",
    "capture_props",
    "search_props",
    "created_at",
    "updated_at",
    "owner_name",
    "site_name",
    "is_public",
)


def _list_fields_for_type(asset_type: ItemType) -> tuple[str, ...]:
    if asset_type == ItemType.DATASET:
        return _DATASET_LIST_FIELDS
    if asset_type == ItemType.CAPTURE:
        return _CAPTURE_LIST_FIELDS
    msg = f"Invalid asset type: {asset_type}"
    raise ValueError(msg)


def _local_list_field_value(
    asset: Dataset | Capture,
    field: str,
    *,
    asset_type: ItemType,
) -> Any:
    if field == "keywords" and isinstance(asset, Dataset):
        value: Any = _keyword_names(asset)
    elif field == "authors" and isinstance(asset, Dataset):
        value = asset.get_authors_display()
    elif field == "status_display" and isinstance(asset, Dataset):
        value = asset.get_status_display()
    elif field == "capture_type_display" and isinstance(asset, Capture):
        value = _capture_type_display(asset.capture_type)
    elif field == "owner_name":
        value = asset.owner.name if asset.owner else "Owner"
    elif field == "site_name":
        value = local_site_name()
    elif isinstance(asset, Capture) and field in _CAPTURE_LOCAL_FIELD_DEFAULTS:
        value = _CAPTURE_LOCAL_FIELD_DEFAULTS[field]
    else:
        value = getattr(asset, field)
    return value


def _apply_peer_doc_to_row(row: dict[str, Any], doc: dict[str, Any]) -> None:
    for key, value in doc.items():
        if key in _LIST_ROW_DATETIME_FIELDS:
            row[key] = _parse_datetime(value)
        else:
            row[key] = value


def _permission_maps_for_user(
    assets: list[Dataset | Capture],
    user: User | None,
    *,
    item_type: ItemType,
) -> tuple[dict[Any, str], set[Any], set[Any]]:
    """Batch-load permission_level, is_shared, is_shared_with_me maps."""
    uuids = [asset.uuid for asset in assets]
    if not uuids:
        return {}, set(), set()

    shared_uuids = set(
        UserSharePermission.objects.filter(
            item_uuid__in=uuids,
            item_type=item_type,
            is_deleted=False,
            is_enabled=True,
        ).values_list("item_uuid", flat=True)
    )

    perm_by_uuid: dict[Any, str] = {}
    shared_with_me: set[Any] = set()
    if user is not None and getattr(user, "is_authenticated", False):
        for asset in assets:
            if asset.owner_id == user.id:
                perm_by_uuid[asset.uuid] = PermissionLevel.OWNER

        user_perms = UserSharePermission.objects.filter(
            item_uuid__in=uuids,
            item_type=item_type,
            shared_with=user,
            is_deleted=False,
            is_enabled=True,
        ).values_list("item_uuid", "permission_level")
        for item_uuid, level in user_perms:
            shared_with_me.add(item_uuid)
            if item_uuid not in perm_by_uuid:
                perm_by_uuid[item_uuid] = level

    return perm_by_uuid, shared_uuids, shared_with_me


def capture_permission_maps_for_user(
    captures: list[Capture],
    user: User | None,
) -> tuple[dict[Any, str], set[Any], set[Any]]:
    return _permission_maps_for_user(captures, user, item_type=ItemType.CAPTURE)


def serialize_local_asset(
    asset: Dataset | Capture,
    user: User | None,
    asset_type: ItemType,
    *,
    permission_level: str | None = None,
    is_shared: bool = False,
    is_shared_with_me: bool = False,
    include_actions: bool = True,
    row_extras: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a list-row dict from a local ORM asset using shared field specs."""
    is_owner = bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and asset.owner_id == user.id
    )
    if permission_level is None and is_owner:
        permission_level = PermissionLevel.OWNER

    row: dict[str, Any] = BASE_ASSET_DICT.copy()
    row["is_owner"] = is_owner
    row["permission_level"] = permission_level
    row["is_shared"] = is_shared
    row["is_shared_with_me"] = is_shared_with_me and not is_owner
    row["is_federated"] = False
    row["site_name"] = local_site_name()
    row["owner_name"] = asset.owner.name if asset.owner else "Owner"

    for field in _list_fields_for_type(asset_type):
        row[field] = _local_list_field_value(asset, field, asset_type=asset_type)

    if asset_type == ItemType.DATASET:
        row["dataset"] = asset
    elif asset_type == ItemType.CAPTURE:
        row["capture"] = asset

    if row_extras:
        row.update(row_extras)

    row["dropdown_menu_items"] = (
        asset_list_dropdown_menu_items(row, asset_type=asset_type)
        if include_actions
        else []
    )
    return row


def serialize_peer_asset(doc: dict[str, Any], asset_type: ItemType) -> dict[str, Any]:
    """Build a list-row dict from a federated OpenSearch ``_source`` document."""
    row: dict[str, Any] = BASE_ASSET_DICT.copy()
    row["is_federated"] = True
    row["can_edit"] = False
    row["can_share"] = False
    row["is_owner"] = False
    row["is_shared"] = False
    row["is_shared_with_me"] = False
    row["permission_level"] = None
    _apply_peer_doc_to_row(row, doc)
    row["dropdown_menu_items"] = []
    if asset_type == ItemType.CAPTURE:
        row["capture_type_display"] = _capture_type_display(row.get("capture_type"))
        row.setdefault("is_public_discovery", False)
        row.setdefault("is_published_discovery", False)
    return row


def serialize_assets_for_user(
    assets: QuerySet[Dataset | Capture] | Iterable[Dataset | Capture],
    user: User | None,
    *,
    asset_type: ItemType,
    include_actions: bool = True,
) -> list[dict[str, Any]]:
    """Serialize local assets into list-row dicts."""
    asset_list = list(assets)
    perm_by_uuid, shared_uuids, shared_with_me = _permission_maps_for_user(
        asset_list,
        user,
        item_type=asset_type,
    )
    return [
        serialize_local_asset(
            asset=asset,
            user=user,
            asset_type=asset_type,
            permission_level=perm_by_uuid.get(asset.uuid),
            is_shared=asset.uuid in shared_uuids,
            is_shared_with_me=asset.uuid in shared_with_me,
            include_actions=include_actions,
        )
        for asset in asset_list
    ]


def serialize_datasets_for_user(
    datasets: QuerySet[Dataset] | Iterable[Dataset],
    user: User | None,
    *,
    include_actions: bool = True,
) -> list[dict[str, Any]]:
    return serialize_assets_for_user(
        datasets,
        user,
        asset_type=ItemType.DATASET,
        include_actions=include_actions,
    )


def build_user_dataset_list_rows(
    user: User,
    owned_datasets: QuerySet[Dataset] | Iterable[Dataset],
    shared_datasets: QuerySet[Dataset] | Iterable[Dataset],
    *,
    sort_by: str = "created_at",
    descending: bool = True,
    query: str | None = None,
) -> list[dict[str, Any]]:
    """Owned, shared, public-on-host, and federated dataset list rows."""
    owned_list = list(owned_datasets)
    shared_list = list(shared_datasets)
    owned_shared = [*owned_list, *shared_list]
    public_extra = published_datasets_excluding(
        owned_shared,
        get_published_datasets().select_related("owner").prefetch_related("keywords"),
    )
    local_rows = [
        *serialize_datasets_for_user(owned_list, user),
        *serialize_datasets_for_user(shared_list, user),
        *serialize_datasets_for_user(public_extra, user),
    ]
    return merge_dataset_list_rows(
        local_rows,
        query=query,
        sort_by=sort_by,
        descending=descending,
    )


def published_captures_excluding(
    captures: Iterable[Capture],
    published_qs: QuerySet[Capture],
) -> list[Capture]:
    seen = {capture.uuid for capture in captures}
    return [capture for capture in published_qs if capture.uuid not in seen]


def published_datasets_excluding(
    datasets: Iterable[Dataset],
    published_qs: QuerySet[Dataset],
) -> list[Dataset]:
    seen = {dataset.uuid for dataset in datasets}
    return [dataset for dataset in published_qs if dataset.uuid not in seen]


def annotate_capture_list_display(row: dict[str, Any]) -> None:
    """Mutually exclusive display flags: owned / shared / public / federated."""
    if row.get("is_federated"):
        row["is_owner"] = False
        row["is_shared_with_me"] = False
        row["is_public_discovery"] = False
        return
    if row.get("is_owner"):
        row["is_shared_with_me"] = False
        row["is_public_discovery"] = False
        return
    if row.get("is_shared_with_me"):
        row["is_public_discovery"] = False
        return
    if not row.get("is_public_discovery"):
        row["is_public_discovery"] = bool(row.get("is_published_discovery"))


def _sort_key_value(row: dict[str, Any], key: str) -> tuple[bool, Any]:
    raw = row.get(key)
    if key in _LIST_ROW_DATETIME_FIELDS:
        value: Any = _parse_datetime(raw)
    else:
        value = raw
    # None sorts after real values when ascending; reverse flips that.
    return (value is None, value)


def merge_asset_list_rows(
    local_rows: list[dict[str, Any]],
    federated_rows: list[dict[str, Any]],
    *,
    sort_by: str = "created_at",
    descending: bool = True,
) -> list[dict[str, Any]]:
    seen = {str(row.get("uuid")) for row in local_rows if row.get("uuid")}
    merged = list(local_rows)
    for fed_row in federated_rows:
        fed_uuid = str(fed_row.get("uuid") or "")
        if fed_uuid and fed_uuid not in seen:
            merged.append(fed_row)
            seen.add(fed_uuid)
    merged.sort(
        key=lambda row: _sort_key_value(row, sort_by),
        reverse=descending,
    )
    return merged


def merge_dataset_list_rows(
    local_rows: list[dict[str, Any]],
    *,
    query: str | None = None,
    sort_by: str = "created_at",
    descending: bool = True,
) -> list[dict[str, Any]]:
    federated_rows = federated_published_dataset_rows(query=query)
    seen = {str(row.get("uuid")) for row in local_rows if row.get("uuid")}
    merged = list(local_rows)
    for fed_row in federated_rows:
        fed_uuid = str(fed_row.get("uuid") or "")
        if fed_uuid and fed_uuid not in seen:
            merged.append(fed_row)
            seen.add(fed_uuid)
    merged.sort(
        key=lambda row: _sort_key_value(row, sort_by),
        reverse=descending,
    )
    return merged


def _parse_freq_bounds_hz(
    min_freq: str | float | None,
    max_freq: str | float | None,
) -> tuple[float | None, float | None]:
    """Parse GHz bounds from list filters into Hz for OpenSearch range queries."""
    min_str = str(min_freq).strip() if min_freq else ""
    max_str = str(max_freq).strip() if max_freq else ""
    min_ghz: float | None
    max_ghz: float | None
    try:
        min_ghz = float(min_str) if min_str else None
    except ValueError:
        min_ghz = None
    try:
        max_ghz = float(max_str) if max_str else None
    except ValueError:
        max_ghz = None
    min_hz = min_ghz * 1e9 if min_ghz is not None else None
    max_hz = max_ghz * 1e9 if max_ghz is not None else None
    return min_hz, max_hz


def federated_capture_list_metadata_filters(
    *,
    date_start: str | None = None,
    date_end: str | None = None,
    min_freq: str | float | None = None,
    max_freq: str | float | None = None,
) -> list[dict[str, Any]]:
    """OpenSearch metadata filters aligned with local capture list filters."""
    filters: list[dict[str, Any]] = []
    start = (date_start or "").strip()
    end = (date_end or "").strip()
    if start or end:
        created_range: dict[str, Any] = {}
        if start:
            created_range["gte"] = start
        if end:
            created_range["lte"] = end
        filters.append(
            {
                "field_path": "created_at",
                "query_type": "range",
                "filter_value": created_range,
            },
        )

    min_hz, max_hz = _parse_freq_bounds_hz(min_freq, max_freq)
    if min_hz is not None or max_hz is not None:
        freq_range: dict[str, Any] = {}
        if min_hz is not None:
            freq_range["gte"] = min_hz
        if max_hz is not None:
            freq_range["lte"] = max_hz
        filters.append(
            {
                "field_path": "search_props.center_frequency",
                "query_type": "range",
                "filter_value": freq_range,
            },
        )
    return filters


def _serialize_peer_asset_rows(
    result: dict[str, Any],
    asset_type: ItemType,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for hit in result.get("hits") or []:
        source = hit.get("source") if isinstance(hit, dict) else None
        if not isinstance(source, dict):
            continue
        peer_row = serialize_peer_asset(source, asset_type)
        if asset_type == ItemType.CAPTURE:
            annotate_capture_list_display(peer_row)
        rows.append(peer_row)
    return rows


def _get_peer_asset_rows(
    *,
    query: str | None = None,
    site: str | None = None,
    asset_type: ItemType,
    capture_type: str | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    if not is_federation_operational():
        return []

    search_func = (
        search_federated_datasets
        if asset_type == ItemType.DATASET
        else search_federated_captures
    )
    try:
        client = get_opensearch_client()
        if asset_type == ItemType.CAPTURE:
            result = search_func(
                client,
                q=query,
                site=site,
                capture_type=capture_type,
                metadata_filters=metadata_filters,
            )
        else:
            result = search_func(
                client,
                q=query,
                site=site,
                metadata_filters=metadata_filters,
            )
    except Exception:
        log.exception(
            "Federated %s search failed; returning local results only",
            asset_type.value,
        )
        return []

    return _serialize_peer_asset_rows(result, asset_type=asset_type)


def get_published_datasets() -> QuerySet[Dataset]:
    return Dataset.objects.filter(
        status=DatasetStatus.FINAL,
        is_public=True,
        is_deleted=False,
    )


def get_published_captures() -> QuerySet[Capture]:
    return Capture.objects.filter(
        is_deleted=False,
        datasets__is_public=True,
        datasets__is_deleted=False,
    ).distinct()


def build_published_asset_list_rows(
    user: User | None,
    *,
    assets: QuerySet[Dataset | Capture] | None = None,
    asset_type: ItemType,
    query: str | None = None,
    site: str | None = None,
) -> list[dict[str, Any]]:
    if assets is None:
        if asset_type == ItemType.DATASET:
            assets = get_published_datasets()
        elif asset_type == ItemType.CAPTURE:
            assets = get_published_captures()
        else:
            msg = f"Invalid asset type: {asset_type}"
            raise ValueError(msg)
    site_filter = (site or "").strip() or None
    local_rows = serialize_assets_for_user(
        assets,
        user,
        asset_type=asset_type,
        include_actions=False,
    )
    if site_filter:
        local_rows = [
            row for row in local_rows if (row.get("site_name") or "") == site_filter
        ]
    federated_rows = _get_peer_asset_rows(
        query=query,
        site=site_filter,
        asset_type=asset_type,
    )
    return merge_asset_list_rows(local_rows, federated_rows)


def build_published_dataset_list_rows(
    user: User | None,
    *,
    datasets: QuerySet[Dataset] | None = None,
    query: str | None = None,
    site: str | None = None,
) -> list[dict[str, Any]]:
    return build_published_asset_list_rows(
        user,
        assets=datasets,
        asset_type=ItemType.DATASET,
        query=query,
        site=site,
    )


def federated_published_capture_rows(
    *,
    query: str | None = None,
    site: str | None = None,
    capture_type: str | None = None,
    metadata_filters: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return _get_peer_asset_rows(
        query=query,
        site=site,
        asset_type=ItemType.CAPTURE,
        capture_type=capture_type,
        metadata_filters=metadata_filters,
    )


def federated_published_dataset_rows(
    *,
    query: str | None = None,
    site: str | None = None,
) -> list[dict[str, Any]]:
    return _get_peer_asset_rows(
        query=query,
        site=site,
        asset_type=ItemType.DATASET,
    )


def merge_capture_list_rows(
    local_rows: list[dict[str, Any]],
    *,
    query: str | None = None,
    capture_type: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
    min_freq: str | float | None = None,
    max_freq: str | float | None = None,
    sort_by: str = "created_at",
    descending: bool = True,
) -> list[dict[str, Any]]:
    cap_type = (capture_type or "").strip() or None
    metadata_filters = federated_capture_list_metadata_filters(
        date_start=date_start,
        date_end=date_end,
        min_freq=min_freq,
        max_freq=max_freq,
    )
    federated_rows = federated_published_capture_rows(
        query=query,
        capture_type=cap_type,
        metadata_filters=metadata_filters or None,
    )
    seen = {str(row.get("uuid")) for row in local_rows if row.get("uuid")}
    merged = list(local_rows)
    for fed_row in federated_rows:
        fed_uuid = str(fed_row.get("uuid") or "")
        if fed_uuid and fed_uuid not in seen:
            merged.append(fed_row)
            seen.add(fed_uuid)
    merged.sort(key=lambda row: _sort_key_value(row, sort_by), reverse=descending)
    return merged
