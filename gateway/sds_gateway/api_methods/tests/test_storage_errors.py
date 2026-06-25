"""Tests for object-store error classification helpers."""

import pytest

from sds_gateway.api_methods.utils.storage_errors import StorageUnavailableError
from sds_gateway.api_methods.utils.storage_errors import is_missing_object_error
from sds_gateway.api_methods.utils.storage_errors import is_storage_unavailable_error


class MissingObjectError(Exception):
    """Test-only exception to simulate missing-object failures."""

    code = "NoSuchKey"


class ServiceUnavailableObjectError(Exception):
    """Test-only exception to simulate storage service failures."""

    code = "ServiceUnavailable"


def test_is_missing_object_error_detects_no_such_key() -> None:
    assert is_missing_object_error(MissingObjectError("missing"))


def test_is_storage_unavailable_error_detects_connection_refused() -> None:
    assert is_storage_unavailable_error(ConnectionRefusedError("refused"))


def test_is_storage_unavailable_error_detects_timeout() -> None:
    assert is_storage_unavailable_error(TimeoutError("timed out"))


def test_is_storage_unavailable_error_detects_urllib3_max_retry() -> None:
    max_retry_error = type(
        "MaxRetryError",
        (Exception,),
        {"__module__": "urllib3.exceptions"},
    )("retries exceeded")

    assert is_storage_unavailable_error(max_retry_error)


def test_is_storage_unavailable_error_does_not_classify_missing_object() -> None:
    assert not is_storage_unavailable_error(MissingObjectError("missing"))


def test_is_storage_unavailable_error_detects_service_unavailable_code() -> None:
    assert is_storage_unavailable_error(
        ServiceUnavailableObjectError("service unavailable"),
    )


def test_storage_unavailable_error_is_os_error() -> None:
    error = StorageUnavailableError("storage down")

    assert isinstance(error, OSError)
    with pytest.raises(StorageUnavailableError):
        raise error
