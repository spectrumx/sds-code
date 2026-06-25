"""Shared predicates for object-store error classification."""

from collections.abc import Iterator
from typing import Final

MISSING_OBJECT_ERROR_CODES: Final[set[str]] = {
    "404",
    "NoSuchBucket",
    "NoSuchKey",
    "NoSuchObject",
    "NoSuchVersion",
    "NotFound",
}

STORAGE_UNAVAILABLE_ERROR_CODES: Final[set[str]] = {
    "InternalError",
    "ServiceUnavailable",
    "SlowDown",
}

STORAGE_UNAVAILABLE_HTTP_STATUS_CODES: Final[set[str]] = {
    "500",
    "502",
    "503",
    "504",
}

STORAGE_UNAVAILABLE_EXCEPTION_NAMES: Final[set[str]] = {
    "ConnectTimeoutError",
    "HostChangedError",
    "MaxRetryError",
    "NewConnectionError",
    "ReadTimeoutError",
}


class StorageUnavailableError(OSError):
    """Raised when object storage is unreachable or otherwise unavailable."""


def _iter_exception_chain(error: BaseException) -> Iterator[BaseException]:
    """Yield *error* and linked causes/contexts without cycles."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def is_missing_object_error(error: Exception) -> bool:
    """Return True when error represents a missing object/bucket condition.

    Handles both MinIO SDK exceptions (``error.code``, ``error.status``)
    and botocore exceptions (``error.response["Error"]["Code"]``).
    """
    for current in _iter_exception_chain(error):
        error_code = str(getattr(current, "code", ""))
        if error_code in MISSING_OBJECT_ERROR_CODES:
            return True

        response = getattr(current, "response", None)
        if isinstance(response, dict):
            code = str(response.get("Error", {}).get("Code", ""))
            if code in MISSING_OBJECT_ERROR_CODES:
                return True

        status_code = str(getattr(current, "status", ""))
        if status_code == "404":
            return True

    return False


def is_storage_unavailable_error(error: Exception) -> bool:
    """Return True when error indicates object storage is unreachable."""
    if is_missing_object_error(error):
        return False

    for current in _iter_exception_chain(error):
        if isinstance(current, (ConnectionError, TimeoutError)):
            return True

        exception_module = type(current).__module__
        exception_name = type(current).__name__
        if (
            exception_module.startswith("urllib3")
            and exception_name in STORAGE_UNAVAILABLE_EXCEPTION_NAMES
        ):
            return True

        error_code = str(getattr(current, "code", ""))
        if error_code in STORAGE_UNAVAILABLE_ERROR_CODES:
            return True

        status_code = str(getattr(current, "status", ""))
        if status_code in STORAGE_UNAVAILABLE_HTTP_STATUS_CODES:
            return True

    return False
