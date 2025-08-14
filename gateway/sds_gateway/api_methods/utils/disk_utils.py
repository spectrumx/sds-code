"""Disk space and file size estimation utilities."""

import shutil
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import QuerySet
from loguru import logger

# Constants for file size limits
DISK_SPACE_BUFFER = 5 * 1024 * 1024 * 1024  # 5 GB buffer for safety


def check_disk_space_available(
    required_bytes: int, directory: Path | None = None
) -> bool:
    """
    Check if there's enough disk space available for the required bytes.

    Args:
        required_bytes: Number of bytes needed
        directory: Directory to check space for (defaults to MEDIA_ROOT)

    Returns:
        bool: True if enough space is available, False otherwise
    """
    if directory is None:
        directory = Path(settings.MEDIA_ROOT)

    try:
        total, used, free = shutil.disk_usage(directory)
        available_space = free - DISK_SPACE_BUFFER
    except (OSError, ValueError) as e:
        logger.error(f"Error checking disk space for {directory}: {e}")
        return False
    else:
        return available_space >= required_bytes


def estimate_disk_size(files: list[Any] | QuerySet | Any) -> int:
    """
    Estimate the size needed on disk for the given files.

    For zip files, this includes compression overhead.
    For other operations, this is just the raw file sizes.

    Args:
        files: List of File model instances or QuerySet

    Returns:
        int: Estimated size in bytes
    """
    # Handle both list and QuerySet
    if hasattr(files, "iterator"):
        # It's a QuerySet
        total_file_size = sum(file_obj.size for file_obj in files.iterator())
    else:
        # It's a list
        total_file_size = sum(file_obj.size for file_obj in files)

    # Estimate zip overhead (headers, compression metadata, etc.)
    # Rough estimate: 10% overhead for small files, 5% for large files
    overhead_factor = 1.1 if total_file_size < 100 * 1024 * 1024 else 1.05

    return int(total_file_size * overhead_factor)


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        str: Formatted size string
    """
    bytes_per_unit = 1024.0
    size_float = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_float < bytes_per_unit:
            return f"{size_float:.1f} {unit}"
        size_float /= bytes_per_unit
    return f"{size_float:.1f} PB"
