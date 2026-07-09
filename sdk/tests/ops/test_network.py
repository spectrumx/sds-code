"""Integration tests with SDS for testing authentication.

Use the integration_client fixture for these tests.
"""

# pyright: reportPrivateUsage=false

# pyright: ignore[reportPrivateUsage]

import sys
from unittest.mock import patch

import pytest
import requests
from spectrumx import errors
from spectrumx.ops.network import extract_error_details_from_html
from spectrumx.ops.network import success_or_raise


def test_success_or_raise_success() -> None:
    """Success should not raise an exception."""
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"
    # No exception = pass; an unexpected exception type surfaces directly.
    success_or_raise(response)


def test_success_or_raise_raises_auth_error_on_401() -> None:
    """AuthError should be raised for a 401 response."""
    response = requests.Response()
    response.status_code = 401
    response._content = b'{"detail": "Unauthorized"}'
    with pytest.raises(errors.AuthError, match="Unauthorized"):
        success_or_raise(response)


def test_success_or_raise_raises_auth_error_on_403() -> None:
    """AuthError should be raised for a 403 response."""
    response = requests.Response()
    response.status_code = 403
    response._content = b'{"detail": "Forbidden"}'
    with pytest.raises(errors.AuthError, match="Forbidden"):
        success_or_raise(response)


def test_success_or_raise_client_error() -> None:
    """A generic SDSError should be raised for 400 responses."""
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"detail": "Bad Request"}'
    with pytest.raises(errors.SDSError, match="Bad Request"):
        success_or_raise(response)


def test_success_or_raise_server_error() -> None:
    """ServiceError should be raised for 500 responses."""
    response = requests.Response()
    response.status_code = 500
    response._content = b'{"detail": "Internal Server Error"}'
    with pytest.raises(errors.ServiceError, match="Internal Server Error"):
        success_or_raise(response, ContextException=errors.SDSError)


def test_success_or_raise_no_context() -> None:
    """SDSError should be raised for client errors when no context is provided."""
    response = requests.Response()
    response.status_code = 418
    response._content = b'{"detail": "I\'m a teapot"}'
    with pytest.raises(errors.SDSError, match="I'm a teapot"):
        success_or_raise(response)


def test_success_or_raise_contextual_exception() -> None:
    """A custom exception should be raised when used as context for client errors."""
    response = requests.Response()
    response.status_code = 400
    response._content = b'{"detail": "Bad Request"}'

    class CustomException(errors.SDSError):
        pass

    with pytest.raises(CustomException, match="Bad Request"):
        success_or_raise(response, ContextException=CustomException)


def test_success_or_raise_no_status_code() -> None:
    """No status code should raise SDSError."""
    response = requests.Response()
    object.__setattr__(response, "status_code", None)
    with pytest.raises(errors.SDSError, match="No status code"):
        success_or_raise(response)


def test_success_or_raise_json_decode_error_no_bs4() -> None:
    """Non-JSON error body falls back to reason when not in test env."""
    response = requests.Response()
    response.status_code = 500
    response._content = b"Not JSON"
    response.reason = "Internal Server Error"
    with (
        patch("spectrumx.ops.network.is_test_env", return_value=False),
        pytest.raises(errors.ServiceError, match="Internal Server Error"),
    ):
        success_or_raise(response)


def test_success_or_raise_json_decode_error_with_bs4() -> None:
    """Non-JSON error body extracts error from HTML when in test env."""
    response = requests.Response()
    response.status_code = 500
    response._content = b'<li id="summary">Error details</li>'
    with (
        patch("spectrumx.ops.network.is_test_env", return_value=True),
        pytest.raises(errors.ServiceError, match="Error details"),
    ):
        success_or_raise(response)


def test_success_or_raise_catchall_fallback() -> None:
    """3xx status falls through to generic SDSError."""
    response = requests.Response()
    response.status_code = 300
    response._content = b'{"detail": "redirected"}'
    with pytest.raises(errors.SDSError, match="redirected"):
        success_or_raise(response)


def test_extract_error_details_from_html_no_matching_element() -> None:
    """When HTML lacks #summary/#pastebinTraceback, falls back to reason."""
    response = requests.Response()
    response.status_code = 500
    response._content = b"<html><body>No useful error element</body></html>"
    response.reason = "Internal Server Error"
    result = extract_error_details_from_html(response)
    assert result == "Internal Server Error"


def test_extract_error_details_from_html_with_bs4() -> None:
    """Extracts text from HTML id=summary element."""
    response = requests.Response()
    response.status_code = 500
    response._content = b'<li id="summary">Extracted error</li>'
    result = extract_error_details_from_html(response)
    assert result == "Extracted error"


def test_extract_error_details_from_html_no_bs4(monkeypatch) -> None:
    """Without bs4, returns response.reason."""
    monkeypatch.setitem(sys.modules, "bs4", None)
    response = requests.Response()
    response.status_code = 500
    response.reason = "Internal Server Error"
    response._content = b""
    result = extract_error_details_from_html(response)
    assert result == "Internal Server Error"


def test_extract_error_details_from_html_no_bs4_no_reason(
    monkeypatch,
) -> None:
    """Without bs4 and no reason, returns 'Unknown reason'."""
    monkeypatch.setitem(sys.modules, "bs4", None)
    response = requests.Response()
    response.status_code = 500
    response.reason = None
    response._content = b""
    result = extract_error_details_from_html(response)
    assert result == "Unknown reason"


def test_extract_error_details_from_html_bs4_no_elements() -> None:
    """When bs4 is available but no matching elements, falls back to reason."""
    response = requests.Response()
    response.status_code = 500
    response._content = b"<html><body>nothing relevant</body></html>"
    response.reason = "Internal Server Error"
    result = extract_error_details_from_html(response)
    assert result == "Internal Server Error"


def test_extract_error_details_from_html_bs4_no_elements_no_reason() -> None:
    """When bs4 available, no elements, reason None, returns 'Unknown reason'."""
    response = requests.Response()
    response.status_code = 500
    response._content = b"<html><body>nothing relevant</body></html>"
    response.reason = None
    result = extract_error_details_from_html(response)
    assert result == "Unknown reason"
