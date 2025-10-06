"""File utility functions for user views."""

import contextlib
import logging
import tempfile
from pathlib import Path

from django.http import JsonResponse

from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_file

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def temp_h5_file_context(file_obj, max_bytes=200 * 1024 * 1024):
    """
    Context manager for safely handling H5 file operations with temporary file.

    Args:
        file_obj: The file object to copy from
        max_bytes: Maximum bytes to copy (default: 200 MiB)

    Yields:
        str: Path to the temporary file

    Raises:
        ValueError: If file is too large to preview
        OSError: If file operations fail
    """
    temp_file = None
    temp_path = None
    try:
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".h5") as temp_file:
            temp_path = temp_file.name

            # Open the source file
            file_obj.file.open("rb")

            # Copy file content to temp file
            bytes_written = 0
            for chunk in file_obj.file.chunks():
                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    error_msg = "File too large to preview"
                    raise ValueError(error_msg)
                temp_file.write(chunk)

            temp_file.flush()

        # Yield the temp file path for processing
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


def check_file_access(file_obj, user):
    """
    Check if user has access to a file object.

    Args:
        file_obj: The file object to check access for
        user: The user requesting access

    Returns:
        bool: True if user has access, False otherwise
    """
    return user_has_access_to_file(user, file_obj)


def validate_h5_file(file_obj, max_bytes=200 * 1024 * 1024):
    """
    Validate that a file is a valid H5 file for preview.

    Args:
        file_obj: The file object to validate
        max_bytes: Maximum file size in bytes

    Returns:
        tuple: (is_valid, error_response) where is_valid is bool and
               error_response is JsonResponse or None
    """

    # Check file extension
    name_lower = (file_obj.name or "").lower()
    if not name_lower.endswith((".h5", ".hdf5")):
        return False, JsonResponse({"error": "Not an HDF5 file"}, status=400)

    # Check file size - if we can't determine size, don't proceed
    try:
        if file_obj.size is None:
            return False, JsonResponse(
                {"error": "Cannot determine file size"}, status=400
            )
        if int(file_obj.size) > max_bytes:
            return False, JsonResponse(
                {"error": "File too large to preview"}, status=413
            )
    except (TypeError, ValueError):
        return False, JsonResponse({"error": "Invalid file size"}, status=400)

    return True, None
