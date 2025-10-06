"""
Utility functions extracted from FilesView class.

These functions were originally methods in the FilesView class but have been
extracted to improve testability and reusability. They can now be tested
independently without needing to instantiate the entire view class.
"""

import contextlib
import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.http import JsonResponse
from django.utils import timezone

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.utils.asset_access_control import (
    user_has_access_to_capture,
)
from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_file

from .item_models import CaptureItem
from .item_models import DatasetItem
from .item_models import DirectoryItem
from .item_models import FileItem
from .item_models import Item


@dataclass
class DirItemParams:
    """Parameters for creating directory items."""

    name: str
    path: str
    uuid: str = ""
    is_capture: bool = False
    is_owner: bool = False
    capture_uuid: str = ""
    modified_at_display: str = "N/A"
    item_count: int | None = None
    is_shared: bool = False
    shared_by: str = ""


@contextlib.contextmanager
def temp_h5_file_context(file_obj, h5_max_bytes: int):
    """Context manager for safely handling H5 file operations with temporary file."""
    temp_file = None
    temp_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".h5") as temp_file:
            temp_path = temp_file.name

            # Copy file content to temp file
            file_obj.file.open("rb")
            bytes_written = 0
            for chunk in file_obj.file.chunks():
                bytes_written += len(chunk)
                if bytes_written > h5_max_bytes:
                    error_msg = "File too large to preview"
                    raise ValueError(error_msg)
                temp_file.write(chunk)
            temp_file.flush()

        yield temp_path
    finally:
        # Clean up source file
        try:
            if hasattr(file_obj.file, "close"):
                file_obj.file.close()
        except OSError:
            pass

        # Clean up temp file
        with contextlib.suppress(OSError):
            if temp_file and not temp_file.closed:
                temp_file.close()

        # Remove temp file from disk
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except OSError as e:
                logger.warning("Could not delete temporary file %s: %s", temp_path, e)


def items_to_dicts(items: list[Item]) -> list[dict[str, Any]]:
    """Convert Pydantic items to dictionaries for templates."""
    return [item.model_dump() for item in items]


def dicts_to_items(data: list[dict[str, Any]]) -> list[Item]:
    """Convert dictionaries to Pydantic items based on type field."""
    items: list[Item] = []
    for item_dict in data:
        item_type = item_dict.get("type")
        if item_type == "file":
            items.append(FileItem(**item_dict))
        elif item_type == "directory":
            items.append(DirectoryItem(**item_dict))
        elif item_type == "capture":
            items.append(CaptureItem(**item_dict))
        elif item_type == "dataset":
            items.append(DatasetItem(**item_dict))
        else:
            logger.warning("Unknown item type: %s", item_type)
    return items


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


def check_file_access(file_obj, user) -> bool:
    """Check if user has access to a file.

    Args:
        file_obj: The file object to check access for
        user: The user requesting access

    Returns:
        bool: True if user has access, False otherwise
    """
    return user_has_access_to_file(user, file_obj)


def validate_h5_file(file_obj, max_bytes: int) -> tuple[bool, JsonResponse | None]:
    """Validate H5 file for preview.

    Args:
        file_obj: The file object to validate
        max_bytes: Maximum bytes allowed for preview

    Returns:
        tuple: (is_valid, error_response) where is_valid is bool and
               error_response is JsonResponse or None
    """
    # Check file extension
    if not file_obj.name.lower().endswith((".h5", ".hdf5")):
        return False, JsonResponse({"error": "File is not an HDF5 file"}, status=400)

    # Check file size
    if file_obj.size is None:
        return False, JsonResponse({"error": "Cannot determine file size"}, status=400)

    try:
        file_size = int(file_obj.size)
        if file_size > max_bytes:
            return False, JsonResponse(
                {"error": "File too large to preview"}, status=413
            )
    except (TypeError, ValueError):
        return False, JsonResponse({"error": "Invalid file size"}, status=400)

    return True, None


def make_dir_item(params: DirItemParams) -> DirectoryItem:
    """Create a standardized directory item."""
    return DirectoryItem(
        name=params.name,
        path=params.path,
        uuid=params.uuid,
        modified_at=params.modified_at_display,
        item_count=params.item_count,
        is_shared=params.is_shared,
        shared_by=params.shared_by,
    )


def make_file_item(
    *,
    file_obj,
    capture_uuid: str = "",
    is_shared: bool = False,
    shared_by: str = "",
) -> FileItem:
    """Create a standardized file item."""
    return FileItem(
        name=file_obj.name,
        path=f"/users/files/{file_obj.uuid}/",
        uuid=str(file_obj.uuid),
        is_capture=False,
        is_shared=is_shared,
        capture_uuid=capture_uuid,
        description=getattr(file_obj, "description", ""),
        modified_at=format_modified(getattr(file_obj, "updated_at", None)),
        shared_by=shared_by,
    )


def add_root_items(request) -> list[Item]:
    """Add captures and datasets to the root directory."""
    items: list[Item] = []

    # Get user's captures
    user_captures = request.user.captures.filter(is_deleted=False)

    logger.debug(
        "FilesView: user=%s has captures=%d",
        request.user.email,
        user_captures.count(),
    )

    # Add captures as folders
    items.extend(
        [
            make_dir_item(
                DirItemParams(
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
            for capture in user_captures
        ]
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

    items.extend(
        [
            make_file_item(
                file_obj=file_obj,
                capture_uuid="",
                is_shared=False,
                shared_by="",
            )
            for file_obj in individual_files
        ]
    )

    return items


def _get_capture_for_user(request, capture_uuid: str) -> Capture | None:
    """Get a capture for the user, checking both owned and shared captures."""

    try:
        capture = Capture.objects.get(uuid=capture_uuid, is_deleted=False)
        if user_has_access_to_capture(request.user, capture):
            return capture
        return None  # noqa: TRY300
    except Capture.DoesNotExist:
        return None


def _normalize_path(path: str) -> str:
    """Normalize a path (no leading/trailing slashes)."""
    return path.strip("/")


def _get_relative_directory(file_obj, capture_root: str, user_root: str) -> str:
    """Get the relative directory path for a file within a capture."""
    file_dir = _normalize_path(file_obj.directory)

    # Start with the most specific root (capture_root), else fall back to user root
    if capture_root and file_dir.startswith(capture_root):
        return file_dir[len(capture_root) :].lstrip("/")

    # Strip '/files/<email>/' if present
    if user_root and file_dir.startswith(user_root):
        rel_dir = file_dir[len(user_root) :].lstrip("/")
    else:
        rel_dir = file_dir

    # If rel_dir begins with the capture folder name, drop it to get inside-capture path
    if "/" in rel_dir:
        _first_seg, rest = rel_dir.split("/", 1)
        return rest  # drop capture folder name

    return rel_dir


def _filter_files_by_subpath(
    files, current_subpath: str, user_root: str = ""
) -> tuple[list, set[str]]:
    """Filter files by subpath and collect child directories."""
    child_dirs: set[str] = set()
    child_files: list = []

    for file_obj in files:
        rel_dir = _get_relative_directory(file_obj, "", user_root)

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
            # File lives directly at this level
            child_files.append(file_obj)
        elif remainder:
            first_component = remainder.split("/", 1)[0]
            # If remainder still has nested components, it's a child dir
            if "/" in remainder:
                child_dirs.add(first_component)
            else:
                # File directly within this level
                child_files.append(file_obj)

    return child_files, child_dirs


def _add_child_directories(
    child_dirs: set[str],
    capture_uuid: str,
    current_subpath: str,
    capture: Capture,
    *,
    is_shared: bool = False,
    shared_by: str = "",
) -> list[Item]:
    """Add child directories to the items list."""
    items: list[Item] = []
    for dirname in sorted(child_dirs):
        # Build the next-level path
        next_path_parts = ["captures", str(capture_uuid)]
        if current_subpath:
            next_path_parts.append(current_subpath)
        next_path_parts.append(dirname)
        next_path = "/" + "/".join(next_path_parts)

        # Use a more friendly name if the directory name looks like an email
        display_name = dirname
        if "@" in dirname and "." in dirname:
            # This looks like an email address, use a more friendly name
            display_name = "Files"

        items.append(
            make_dir_item(
                DirItemParams(
                    name=display_name,
                    path=next_path,
                    uuid="",
                    is_capture=False,
                    is_shared=is_shared,
                    is_owner=not is_shared,  # Only owned if not shared
                    capture_uuid=str(capture_uuid),
                    modified_at_display=format_modified(
                        getattr(capture, "updated_at", None)
                    ),
                    shared_by=shared_by,
                )
            )
        )
    return items


def _add_child_files(
    child_files: list,
    capture_uuid: str,
    *,
    is_shared: bool = False,
    shared_by: str = "",
) -> list[Item]:
    """Add child files to the items list."""
    return [
        make_file_item(
            file_obj=file_obj,
            capture_uuid=str(capture_uuid),
            is_shared=is_shared,
            shared_by=shared_by,
        )
        for file_obj in sorted(child_files, key=lambda f: f.name.lower())
    ]


def add_capture_files(request, capture_uuid, subpath: str = "") -> list[Item]:
    """Add nested directories/files within a specific capture.

    Displays only the immediate children (directories and files) of the
    provided subpath within the capture, preserving the nested structure.
    """
    # Get the capture (owned or shared)
    capture = _get_capture_for_user(request, capture_uuid)
    if not capture:
        return []

    # Check if this is a shared capture (not owned by current user)
    is_shared = capture.owner != request.user
    shared_by = capture.owner.email if is_shared else ""

    # Get files associated with this capture
    capture_files = get_filtered_files_queryset(
        File.objects.filter(capture=capture, is_deleted=False)
    )

    logger.debug(
        "FilesView: capture=%s files=%d is_shared=%s",
        capture.name,
        capture_files.count(),
        is_shared,
    )

    # Normalize paths
    current_subpath = _normalize_path(subpath)

    # For shared captures, use the original owner's email path, not current user's
    if is_shared:
        user_root = _normalize_path(f"files/{capture.owner.email}")
    else:
        user_root = _normalize_path(f"files/{request.user.email}")

    # Filter files by subpath and collect child directories
    child_files, child_dirs = _filter_files_by_subpath(
        capture_files, current_subpath, user_root
    )

    # Add child directories first
    directory_items = _add_child_directories(
        child_dirs, capture_uuid, current_subpath, capture, is_shared, shared_by
    )

    # Then add files that live directly in this level
    file_items = _add_child_files(child_files, capture_uuid, is_shared, shared_by)

    return directory_items + file_items


def add_shared_items(request) -> list[Item]:
    """Add shared captures and datasets, avoiding N+1 lookups."""
    items: list[Item] = []

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

    items.extend(
        [
            make_dir_item(
                DirItemParams(
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
            for capture in shared_captures
        ]
    )

    return items


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
            except (ValueError, TypeError, AttributeError):
                # Handle UUID parsing errors, type errors, or attribute access issues
                # These are expected during name resolution and should fall back
                return str(part)
        return str(part)

    for i, part in enumerate(path_parts):
        # Skip noisy storage and container segments
        if part in {"files", user_email, "captures"}:
            continue

        # Skip email addresses (anything with @ and .)
        if "@" in part and "." in part:
            continue

        breadcrumb_parts.append(
            {
                "name": resolve_name(i, part),
                "path": "/" + "/".join(path_parts[: i + 1]),
            }
        )

    return breadcrumb_parts
