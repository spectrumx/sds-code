"""Shared predicates for object-store error classification."""

from typing import Final

MISSING_OBJECT_ERROR_CODES: Final[set[str]] = {
    "404",
    "NoSuchBucket",
    "NoSuchKey",
    "NoSuchObject",
    "NoSuchVersion",
    "NotFound",
}


def is_missing_object_error(error: Exception) -> bool:
    """Return True when error represents a missing object/bucket condition.

    Handles both MinIO SDK exceptions (``error.code``, ``error.status``)
    and botocore exceptions (``error.response["Error"]["Code"]``).
    """
    error_code = str(getattr(error, "code", ""))
    if error_code in MISSING_OBJECT_ERROR_CODES:
        return True

    response = getattr(error, "response", None)
    if isinstance(response, dict):
        code = str(response.get("Error", {}).get("Code", ""))
        if code in MISSING_OBJECT_ERROR_CODES:
            return True

    status_code = str(getattr(error, "status", ""))
    return status_code == "404"
