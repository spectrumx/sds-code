"""
Utility functions extracted from FilesView class.

These functions were originally methods in the FilesView class but have been
extracted to improve testability and reusability. They can now be tested
independently without needing to instantiate the entire view class.
"""

import logging

from django.utils import timezone

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission

logger = logging.getLogger(__name__)


def get_filtered_files_queryset(base_queryset):
    """
    Apply common file filtering to exclude system files and hidden files.

    Args:
        base_queryset: Base File queryset to filter

    Returns:
        QuerySet: Filtered queryset excluding system files
    """
    return (
        base_queryset.exclude(name__endswith=".DS_Store")
        .exclude(name__startswith=".")
        .exclude(name__in=[".DS_Store", "._.DS_Store", "Thumbs.db", "desktop.ini"])
    )


def format_modified(dt: timezone.datetime | None) -> str:
    """Return a consistent display string for modified timestamps."""
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "N/A"


def make_dir_item(
    *,
    name: str,
    path: str,
    uuid: str = "",
    is_capture: bool = False,
    is_shared: bool = False,
    is_owner: bool = False,
    capture_uuid: str = "",
    modified_at_display: str = "N/A",
    shared_by: str = "",
) -> dict:
    """Create a standardized directory item dict for the template."""
    return {
        "type": "directory",
        "name": name,
        "path": path,
        "uuid": uuid,
        "is_capture": is_capture,
        "is_shared": is_shared,
        "is_owner": is_owner,
        "capture_uuid": capture_uuid,
        "modified_at": modified_at_display,
        "shared_by": shared_by,
    }


def make_file_item(
    *,
    file_obj,
    capture_uuid: str = "",
    is_shared: bool = False,
    shared_by: str = "",
) -> dict:
    """Create a standardized file item dict for the template."""
    return {
        "type": "file",
        "name": file_obj.name,
        "path": f"/users/files/{file_obj.uuid}/",
        "uuid": str(file_obj.uuid),
        "is_capture": False,
        "is_shared": is_shared,
        "capture_uuid": capture_uuid,
        "description": getattr(file_obj, "description", ""),
        "modified_at": format_modified(getattr(file_obj, "updated_at", None)),
        "shared_by": shared_by,
    }


def add_root_items(request, items):
    """Add captures and datasets to the root directory."""
    # Get user's captures
    user_captures = request.user.captures.filter(is_deleted=False)

    logger.debug(
        "FilesView: user=%s has captures=%d",
        request.user.email,
        user_captures.count(),
    )

    # Add captures as folders
    for capture in user_captures:
        items.append(
            make_dir_item(
                name=capture.name or f"Capture {capture.uuid}",
                path=f"/captures/{capture.uuid}",
                uuid=str(capture.uuid),
                is_capture=True,
                is_shared=False,
                is_owner=True,  # User owns their own captures
                capture_uuid=str(capture.uuid),
                modified_at_display=format_modified(
                    getattr(capture, "updated_at", None)
                ),
                shared_by="",
            )
        )

    # Add individual files that are not part of any capture
    individual_files = get_filtered_files_queryset(
        File.objects.filter(
            owner=request.user,
            is_deleted=False,
            capture__isnull=True,
        )
    ).order_by("name")

    logger.debug(
        "FilesView: user=%s has individual files=%d",
        request.user.email,
        individual_files.count(),
    )

    for file_obj in individual_files:
        items.append(
            make_file_item(
                file_obj=file_obj,
                capture_uuid="",
                is_shared=False,
                shared_by="",
            )
        )

    # Note: _add_shared_items will be called separately from the view


def add_capture_files(request, items, capture_uuid, subpath: str = ""):  # noqa: C901, PLR0912, PLR0915
    """Add nested directories/files within a specific capture.

    Displays only the immediate children (directories and files) of the
    provided subpath within the capture, preserving the nested structure.
    """
    try:
        capture = request.user.captures.get(uuid=capture_uuid, is_deleted=False)
    except Capture.DoesNotExist:
        # Check if it's shared
        shared_permission = UserSharePermission.objects.filter(
            item_uuid=capture_uuid,
            item_type=ItemType.CAPTURE,
            shared_with=request.user,
            is_deleted=False,
            is_enabled=True,
        ).first()
        if shared_permission:
            capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)
        else:
            return

    # Get files associated with this capture
    capture_files = get_filtered_files_queryset(
        File.objects.filter(capture=capture, is_deleted=False)
    )

    logger.debug(
        "FilesView: capture=%s files=%d",
        capture.name,
        capture_files.count(),
    )

    # Normalize helper
    def _norm(path: str) -> str:
        """Normalize a path (no leading/trailing slashes)."""
        return path.strip("/")

    capture_root = _norm(capture.top_level_dir or "")
    current_subpath = _norm(subpath)
    user_root = _norm(f"files/{request.user.email}")

    # Collect immediate child directories and files under current_subpath
    child_dirs: set[str] = set()
    child_files: list = []

    for file_obj in capture_files:
        # Build the directory relative to the capture's top level dir
        file_dir = _norm(file_obj.directory)

        # Start with the most specific root (capture_root),
        # else fall back to user root
        rel_dir = file_dir
        if capture_root and file_dir.startswith(capture_root):
            rel_dir = file_dir[len(capture_root) :].lstrip("/")
        else:
            # Strip '/files/<email>/' if present
            if user_root and file_dir.startswith(user_root):
                rel_dir = file_dir[len(user_root) :].lstrip("/")
            # If rel_dir begins with the capture folder name,
            # drop it to get inside-capture path
            if "/" in rel_dir:
                _first_seg, rest = rel_dir.split("/", 1)
                rel_dir = rest  # drop capture folder name
            else:
                rel_dir = ""

        # If we're inside a subpath, filter to entries within that subpath
        if current_subpath:
            if rel_dir == current_subpath:
                # File directly in current subpath
                child_files.append(file_obj)
                continue
            if rel_dir.startswith(current_subpath + "/"):
                remainder = rel_dir[len(current_subpath) + 1 :]
            else:
                # This file is not under the current subpath
                continue
        else:
            remainder = rel_dir

        # Determine if this file belongs to an immediate child directory
        if not remainder:
            # File lives directly at this level (capture root or current subpath)
            child_files.append(file_obj)
        elif remainder:
            first_component = remainder.split("/", 1)[0]
            # If remainder still has nested components, it's a child dir
            if "/" in remainder:
                child_dirs.add(first_component)
            else:
                # File directly within this level
                child_files.append(file_obj)

    # Add immediate child directories first
    for dirname in sorted(child_dirs):
        # Build the next-level path
        next_path_parts = ["captures", str(capture_uuid)]
        if current_subpath:
            next_path_parts.append(current_subpath)
        next_path_parts.append(dirname)
        next_path = "/" + "/".join(next_path_parts)
        items.append(
            make_dir_item(
                name=dirname,
                path=next_path,
                uuid="",
                is_capture=False,
                is_shared=False,
                is_owner=True,  # Directories within user's own captures
                capture_uuid=str(capture_uuid),
                modified_at_display=format_modified(
                    getattr(capture, "updated_at", None)
                ),
                shared_by="",
            )
        )

    # Then add files that live directly in this level
    for file_obj in sorted(child_files, key=lambda f: f.name.lower()):
        items.append(
            make_file_item(
                file_obj=file_obj,
                capture_uuid=str(capture_uuid),
                is_shared=False,
                shared_by="",
            )
        )


def add_shared_items(request, items):
    """Add shared captures and datasets, avoiding N+1 lookups."""
    shared_permissions = (
        UserSharePermission.objects.filter(
            shared_with=request.user,
            is_deleted=False,
            is_enabled=True,
        )
        .select_related("owner")
        .only("item_uuid", "item_type", "owner__email")
    )

    # Build mapping from item_uuid to owner email by type
    capture_owner_by_uuid: dict[str, str] = {}
    capture_uuids: list[str] = []
    for perm in shared_permissions:
        if perm.item_type == ItemType.CAPTURE:
            capture_uuids.append(str(perm.item_uuid))
            capture_owner_by_uuid[str(perm.item_uuid)] = getattr(
                perm.owner, "email", "Unknown"
            )

    # Fetch items (excluding user's own)
    shared_captures = Capture.objects.filter(
        uuid__in=capture_uuids, is_deleted=False
    ).exclude(owner=request.user)

    for capture in shared_captures:
        items.append(
            make_dir_item(
                name=capture.name or f"Capture {capture.uuid}",
                path=f"/captures/{capture.uuid}",
                uuid=str(capture.uuid),
                is_capture=True,
                is_shared=True,
                is_owner=False,  # Shared items are not owned by current user
                capture_uuid=str(capture.uuid),
                modified_at_display=format_modified(
                    getattr(capture, "updated_at", None)
                ),
                shared_by=capture_owner_by_uuid.get(str(capture.uuid), "Unknown"),
            )
        )


def build_breadcrumbs(current_dir, user_email: str):
    """Build breadcrumb navigation with friendly names.

    - Skips technical segments like "files", the user's email, and
      container segments ("captures", "datasets").
    - Resolves UUID segments to item names for captures/datasets when possible.
    """
    breadcrumb_parts: list[dict[str, str]] = []
    if current_dir == "/":
        return breadcrumb_parts

    path_parts = current_dir.strip("/").split("/")

    def resolve_name(index: int, part: str) -> str:
        # Resolve UUID to a human-friendly name for captures
        if index > 0 and path_parts[0] == "captures" and index == 1:
            try:
                obj = Capture.objects.only("name").filter(uuid=part).first()
                return obj.name or str(part) if obj else str(part)
            except Exception:  # noqa: BLE001 - resolving display names is best-effort
                return str(part)
        return str(part)

    for i, part in enumerate(path_parts):
        # Skip noisy storage and container segments
        if part in {"files", user_email, "captures"}:
            continue
        breadcrumb_parts.append(
            {
                "name": resolve_name(i, part),
                "path": "/" + "/".join(path_parts[: i + 1]),
            }
        )

    return breadcrumb_parts
