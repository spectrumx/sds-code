"""Discover files under a capture path that would change on capture update (reindex)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Literal

from sds_gateway.api_methods.helpers.reconstruct_file_tree import (
    _get_list_of_capture_files,
)
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.relationship_utils import get_capture_files
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user

if TYPE_CHECKING:
    from sds_gateway.users.models import User

ReindexCandidateStatus = Literal["not_linked", "updated"]


def _normalize_directory(directory: str) -> str:
    return str(directory).rstrip("/")


def resolve_capture_virtual_top_dir(capture: Capture, owner: User) -> Path | None:
    """Virtual directory prefix used for file discovery (matches ingest_capture)."""
    requested = sanitize_path_rel_to_user(
        unsafe_path=capture.top_level_dir,
        user=owner,
    )
    if requested is None:
        return None
    top_level_dir = Path(requested)
    user_file_prefix = f"/files/{owner.email!s}"
    if not str(top_level_dir).startswith(user_file_prefix):
        top_level_dir = Path(f"{user_file_prefix!s}{top_level_dir!s}")
    return top_level_dir


def classify_reindex_candidates(
    eligible_files: list[File],
    linked_files: list[File],
) -> list[dict[str, Any]]:
    """Compare eligible tree files to capture-linked files by path and checksum."""
    linked_by_path = {
        (_normalize_directory(f.directory), f.name): f for f in linked_files
    }
    linked_ids = {f.uuid for f in linked_files}

    candidates: list[dict[str, Any]] = []
    seen_paths: set[tuple[str, str]] = set()

    for file_obj in eligible_files:
        path_key = (_normalize_directory(file_obj.directory), file_obj.name)
        if path_key in seen_paths:
            continue
        seen_paths.add(path_key)

        linked = linked_by_path.get(path_key)
        if linked is None:
            if file_obj.uuid not in linked_ids:
                candidates.append(_serialize_candidate(file_obj, "not_linked"))
            continue

        checksum_changed = (
            bool(linked.sum_blake3)
            and bool(file_obj.sum_blake3)
            and linked.sum_blake3 != file_obj.sum_blake3
        )
        identity_changed = linked.uuid != file_obj.uuid
        if identity_changed or checksum_changed:
            candidates.append(_serialize_candidate(file_obj, "updated"))

    return candidates


def _serialize_candidate(
    file_obj: File,
    status: ReindexCandidateStatus,
) -> dict[str, Any]:
    return {
        "uuid": str(file_obj.uuid),
        "directory": file_obj.directory,
        "name": file_obj.name,
        "size": file_obj.size,
        "status": status,
        "sum_blake3": file_obj.sum_blake3 or "",
    }


def get_capture_reindex_candidates(capture: Capture) -> list[dict[str, Any]]:
    """Files under the capture tree not linked or replaced at the same path."""
    owner = capture.owner
    if owner is None:
        return []

    virtual_top_dir = resolve_capture_virtual_top_dir(capture, owner)
    if virtual_top_dir is None:
        return []

    cap_type = CaptureType(capture.capture_type)
    eligible_qs = _get_list_of_capture_files(
        capture_type=cap_type,
        virtual_top_dir=virtual_top_dir,
        owner=owner,
        drf_channel=capture.channel if cap_type == CaptureType.DigitalRF else None,
        rh_scan_group=capture.scan_group
        if cap_type == CaptureType.RadioHound
        else None,
    )
    eligible = list(eligible_qs.order_by("directory", "name"))
    linked = list(get_capture_files(capture))
    return classify_reindex_candidates(eligible, linked)
