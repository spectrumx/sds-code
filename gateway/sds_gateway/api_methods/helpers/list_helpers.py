"""Lightweight list-row adapters for local and federated dataset UI lists."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from django.urls import reverse
from django.utils import dateparse
from django.utils import timezone

from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import PermissionLevel
from sds_gateway.api_methods.models import UserSharePermission

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet

    from sds_gateway.api_methods.models import Dataset
    from sds_gateway.users.models import User


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


def dataset_list_dropdown_menu_items(row: dict[str, Any]) -> list[dict[str, Any]]:
    """Build dropdown_menu.html items for a serialized dataset list row."""
    if row.get("is_federated"):
        return []

    uuid = str(row.get("uuid") or "")
    if not uuid:
        return []

    is_owner = row.get("is_owner")
    permission_level = row.get("permission_level")
    is_contributor = permission_level == PermissionLevel.CONTRIBUTOR
    is_co_owner = permission_level == PermissionLevel.CO_OWNER
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
                    "asset-type": "dataset",
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


def _permission_maps_for_user(
    datasets: list[Dataset],
    user: User | None,
) -> tuple[dict[Any, str], set[Any], set[Any]]:
    """Batch-load permission_level, is_shared, is_shared_with_me maps."""
    uuids = [ds.uuid for ds in datasets]
    if not uuids:
        return {}, set(), set()

    shared_uuids = set(
        UserSharePermission.objects.filter(
            item_uuid__in=uuids,
            item_type=ItemType.DATASET,
            is_deleted=False,
            is_enabled=True,
        ).values_list("item_uuid", flat=True)
    )

    perm_by_uuid: dict[Any, str] = {}
    shared_with_me: set[Any] = set()
    if user is not None and getattr(user, "is_authenticated", False):
        for ds in datasets:
            if ds.owner_id == user.id:
                perm_by_uuid[ds.uuid] = PermissionLevel.OWNER

        user_perms = UserSharePermission.objects.filter(
            item_uuid__in=uuids,
            item_type=ItemType.DATASET,
            shared_with=user,
            is_deleted=False,
            is_enabled=True,
        ).values_list("item_uuid", "permission_level")
        for item_uuid, level in user_perms:
            shared_with_me.add(item_uuid)
            if item_uuid not in perm_by_uuid:
                perm_by_uuid[item_uuid] = level

    return perm_by_uuid, shared_uuids, shared_with_me


def serialize_local_dataset_row(
    dataset: Dataset,
    user: User | None = None,
    *,
    permission_level: str | None = None,
    is_shared: bool = False,
    is_shared_with_me: bool = False,
    include_actions: bool = True,
) -> dict[str, Any]:
    """Build a lightweight list-row dict for a local Dataset ORM instance."""
    is_owner = bool(
        user is not None
        and getattr(user, "is_authenticated", False)
        and dataset.owner_id == user.id
    )
    if permission_level is None and is_owner:
        permission_level = PermissionLevel.OWNER

    row: dict[str, Any] = {
        "uuid": dataset.uuid,
        "name": dataset.name,
        "version": dataset.version,
        "authors": dataset.get_authors_display(),
        "keywords": _keyword_names(dataset),
        "created_at": dataset.created_at,
        "updated_at": dataset.updated_at,
        "site_name": local_site_name(),
        "is_federated": False,
        "is_public": dataset.is_public,
        "status": dataset.status,
        "status_display": dataset.get_status_display(),
        "owner_name": dataset.owner.name if dataset.owner else "Owner",
        "is_owner": is_owner,
        "is_shared": is_shared,
        "is_shared_with_me": is_shared_with_me and not is_owner,
        "permission_level": permission_level,
        # Keep ORM for existing list modals that still read ``row.dataset``.
        "dataset": dataset,
    }
    row["dropdown_menu_items"] = (
        dataset_list_dropdown_menu_items(row) if include_actions else []
    )
    return row


def serialize_federated_dataset_row(doc: dict[str, Any]) -> dict[str, Any]:
    """Normalize a fed-datasets OpenSearch ``_source`` into a list-row dict."""
    return {
        "uuid": doc.get("uuid"),
        "name": doc.get("name") or "",
        "version": doc.get("version", 1),
        "authors": doc.get("authors") or [],
        "keywords": doc.get("keywords") or [],
        "created_at": _parse_datetime(doc.get("created_at")),
        "updated_at": _parse_datetime(doc.get("updated_at")),
        "site_name": doc.get("site_name") or "",
        "is_federated": True,
        "is_public": bool(doc.get("is_public", True)),
        "status": doc.get("status") or DatasetStatus.FINAL,
        "status_display": doc.get("status_display") or "Final",
        "owner_name": doc.get("owner_name") or "",
        "abstract": doc.get("abstract") or "",
        "description": doc.get("description") or "",
        "is_owner": False,
        "is_shared": False,
        "is_shared_with_me": False,
        "permission_level": None,
        "can_edit": False,
        "can_share": False,
        "dropdown_menu_items": [],
    }


def serialize_datasets_for_user(
    datasets: QuerySet[Dataset] | Iterable[Dataset],
    user: User | None,
    *,
    include_actions: bool = True,
) -> list[dict[str, Any]]:
    """Serialize local datasets into list-row dicts (no heavy API serializer)."""
    dataset_list = list(datasets)
    perm_by_uuid, shared_uuids, shared_with_me = _permission_maps_for_user(
        dataset_list,
        user,
    )
    return [
        serialize_local_dataset_row(
            dataset,
            user,
            permission_level=perm_by_uuid.get(dataset.uuid),
            is_shared=dataset.uuid in shared_uuids,
            is_shared_with_me=dataset.uuid in shared_with_me,
            include_actions=include_actions,
        )
        for dataset in dataset_list
    ]


def _sort_key_value(row: dict[str, Any], key: str) -> tuple[bool, Any]:
    value = row.get(key)
    # None sorts after real values when ascending; reverse flips that.
    return (value is None, value)


def merge_dataset_list_rows(
    local_rows: list[dict[str, Any]],
    federated_rows: list[dict[str, Any]],
    *,
    sort_by: str = "created_at",
    descending: bool = True,
) -> list[dict[str, Any]]:
    """Merge local + federated list rows and sort by a shared field."""
    merged = [*local_rows, *federated_rows]
    merged.sort(
        key=lambda row: _sort_key_value(row, sort_by),
        reverse=descending,
    )
    return merged
