"""File utility functions for user views."""

import contextlib
import json
import logging
import tempfile
from pathlib import Path

from django.http import HttpResponse
from django.http import JsonResponse

from sds_gateway.api_methods.utils.asset_access_control import user_has_access_to_file

logger = logging.getLogger(__name__)


class PreviewFileTooLargeError(Exception):
    """Raised when a file is too large to generate a preview."""


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
        PreviewFileTooLargeError: If file is too large to preview
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
                    raise PreviewFileTooLargeError(error_msg)
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


def validate_file_preview_request(user, file_obj, max_bytes):
    """
    Validate a file preview request.

    Args:
        user: The user requesting the preview
        file_obj: The file object to preview
        max_bytes: Maximum file size allowed for preview

    Returns:
        JsonResponse or None: Error response if validation fails, None if valid
    """
    # Access control: owner or shared via capture/dataset
    has_access = user_has_access_to_file(user, file_obj)
    if not has_access:
        return JsonResponse({"error": "Not found or access denied"}, status=404)

    # Size guard
    if file_obj.size and int(file_obj.size) > max_bytes:
        return JsonResponse({"error": "File too large to preview"}, status=413)

    return None


def get_file_content_response(file_obj, max_bytes):
    """
    Read file content and return appropriate HTTP response.

    Supports pretty-printing JSON files based on extension.

    Args:
        file_obj: The file object to read
        max_bytes: Maximum bytes to read

    Returns:
        HttpResponse: Response with file content as text

    Raises:
        OSError: If file reading fails
    """
    # Read content
    file_obj.file.open("rb")
    raw = file_obj.file.read(max_bytes + 1)
    file_obj.file.close()

    if len(raw) > max_bytes:
        return JsonResponse({"error": "File too large to preview"}, status=413)

    # Detect JSON by extension
    name_lower = (file_obj.name or "").lower()
    if name_lower.endswith(".json"):
        try:
            parsed = json.loads(raw.decode("utf-8"))
            pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
            return HttpResponse(pretty, content_type="text/plain; charset=utf-8")
        except (UnicodeDecodeError, json.JSONDecodeError):
            # fall through to plain text rendering below
            pass

    # Default: return UTF-8 text
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        # Replace undecodable bytes
        text = raw.decode("utf-8", errors="replace")

    return HttpResponse(text, content_type="text/plain; charset=utf-8")
