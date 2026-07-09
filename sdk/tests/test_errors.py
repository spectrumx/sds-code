"""Tests for the errors module."""

from unittest.mock import MagicMock

import pytest
from spectrumx.errors import AuthError
from spectrumx.errors import CaptureError
from spectrumx.errors import NetworkError
from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.errors import Unset
from spectrumx.errors import UploadError
from spectrumx.errors import process_upload_results
from spectrumx.models.files.file import File

# =============================================================================
# SDSError base
# =============================================================================


def test_sds_error_str_returns_message() -> None:
    """SDSError.__str__ returns the message."""
    err = SDSError("test message")
    assert str(err) == "test message"


def test_auth_error_is_subclass_of_sds_error() -> None:
    """AuthError is a subclass of SDSError."""
    err = AuthError("auth failed")
    assert isinstance(err, SDSError)


def test_network_error_is_subclass_of_sds_error() -> None:
    """NetworkError is a subclass of SDSError."""
    err = NetworkError("network failed")
    assert isinstance(err, SDSError)


# =============================================================================
# CaptureError.extract_existing_capture_uuid
# =============================================================================


def test_extract_existing_capture_uuid_no_marker() -> None:
    """Returns None when no 'drf_unique_channel_and_tld' in message."""
    err = CaptureError("some other error")
    assert err.extract_existing_capture_uuid() is None


def test_extract_existing_capture_uuid_with_uuid() -> None:
    """Returns UUID when present in the expected format."""
    uuid_str = "12345678-1234-5678-1234-567812345678"
    err = CaptureError(f"drf_unique_channel_and_tld another capture: {uuid_str}")
    result = err.extract_existing_capture_uuid()
    assert result == uuid_str


def test_extract_existing_capture_uuid_malformed() -> None:
    """Returns something (not None) when marker present but format is unexpected."""
    err = CaptureError("drf_unique_channel_and_tld")
    result = err.extract_existing_capture_uuid()
    # The function does not raise; it tries to parse and returns a best-effort string
    assert isinstance(result, str)


# =============================================================================
# UploadError
# =============================================================================


def test_upload_error_creation() -> None:
    """UploadError can be created with message, File, and reason."""
    mock_file = MagicMock(spec=File)
    err = UploadError(
        message="upload failed",
        sds_file=mock_file,
        reason="timeout",
    )
    assert isinstance(err, UploadError)


def test_upload_error_attributes() -> None:
    """UploadError has correct sds_file and reason attributes."""
    mock_file = MagicMock(spec=File)
    err = UploadError(
        message="upload failed",
        sds_file=mock_file,
        reason="timeout",
    )
    assert err.sds_file is mock_file
    assert err.reason == "timeout"


# =============================================================================
# Unset
# =============================================================================


def test_unset_eq_returns_true_for_unset() -> None:
    """Unset.__eq__ returns True for another Unset instance."""
    assert Unset() == Unset()


def test_unset_eq_returns_false_for_non_unset() -> None:
    """Unset.__eq__ returns False for non-Unset."""
    assert Unset() != object()
    assert Unset() != 42
    assert Unset() != "string"


def test_unset_hash_works() -> None:
    """Unset.__hash__ works (doesn't raise)."""
    # The singleton makes all Unset instances the same object
    s = {Unset(), Unset()}
    assert len(s) == 1


# =============================================================================
# Result
# =============================================================================


def test_result_rejects_value_that_is_an_exception() -> None:
    """Result with value=Exception raises ValueError."""
    with pytest.raises(ValueError, match="Value cannot be an instance of Exception"):
        Result(value=Exception("test"))


def test_result_str_success() -> None:
    """Result.__str__ for success case."""
    result = Result(value=42)
    # Keeps signal if repr formatting changes, still pins the contract.
    assert "Result(value=42)" in str(result)


def test_result_value_returns_value_on_success() -> None:
    """The ``value`` property returns the wrapped value on a successful Result."""
    assert Result(value=7).value == 7


def test_result_str_failure() -> None:
    """Result.__str__ for failure case."""
    result = Result(exception=ValueError("bad"))
    assert "Result(exception=" in str(result)
    assert "bad" in str(result)


def test_result_call_raises_exception() -> None:
    """Result.__call__ raises stored exception."""
    result = Result(exception=ValueError("bad"))
    with pytest.raises(ValueError, match="bad"):
        result()


def test_result_exception_or_returns_default_on_success() -> None:
    """Result.exception_or returns default when result is success."""
    result = Result(value=42)
    default = ValueError("default")
    assert result.exception_or(default) is default


def test_result_value_or_returns_default_on_failure() -> None:
    """Result.value_or returns default when result is a failure."""
    result = Result(exception=ValueError("bad"))
    assert result.value_or("default") == "default"


def test_result_unwrap_returns_value() -> None:
    """Result.unwrap returns the wrapped value."""
    result = Result(value=42)
    assert result.unwrap() == 42


def test_result_value_raises_on_failure() -> None:
    """Result.value raises the stored exception when result is a failure."""
    result = Result(exception=ValueError("bad"))
    with pytest.raises(ValueError, match="bad"):
        _ = result.value


# =============================================================================
# process_upload_results
# =============================================================================


def test_process_upload_results_all_successful() -> None:
    """Returns True when all uploads are successful."""
    results = [Result(value="file1"), Result(value="file2")]
    assert process_upload_results(results, verbose=False, raise_on_error=False) is True


def test_process_upload_results_raises_on_error() -> None:
    """When raise_on_error=True and there are failures, raises the first exception."""
    results = [
        Result(exception=ValueError("first error")),
        Result(value="ok"),
    ]
    with pytest.raises(ValueError, match="first error"):
        process_upload_results(results, verbose=False, raise_on_error=True)


def test_process_upload_results_returns_false_verbose() -> None:
    """When raise_on_error=False and verbose=True, returns False."""
    results = [Result(exception=ValueError("fail"))]
    assert process_upload_results(results, verbose=True, raise_on_error=False) is False


@pytest.mark.parametrize("verbose", [True, False])
def test_process_upload_results_no_results_returns_false(
    verbose: bool,
) -> None:
    """Returns False when there are no results, regardless of verbose."""
    assert process_upload_results([], verbose=verbose, raise_on_error=False) is False


def test_process_upload_results_failed_with_falsy_exception() -> None:
    """When raise_on_error=True and failed_uploads exist but exception_or
    returns a falsy value, iterates through all and raises on the first
    truthy exception."""

    class FalsyError(Exception):
        def __bool__(self) -> bool:
            return False

    results = [
        Result(exception=FalsyError("skip")),
        Result(exception=ValueError("actual error")),
    ]
    with pytest.raises(ValueError, match="actual error"):
        process_upload_results(results, verbose=False, raise_on_error=True)
