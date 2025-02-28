"""Integration tests with SDS for testing authentication.

Use the integration_client fixture for these tests.
"""

# ruff: noqa: SLF001

import pytest
import requests
from spectrumx import errors
from spectrumx.ops.network import success_or_raise


def test_success_or_raise_success() -> None:
    """Success should not raise an exception."""
    response = requests.Response()
    response.status_code = 200
    response._content = b"{}"
    try:
        success_or_raise(response)
    except errors.SDSError:
        pytest.fail("SDSError raised on successful response")


def test_success_or_raise_auth_error() -> None:
    """AuthError should be raised for 401 and 403 responses."""
    response = requests.Response()
    response.status_code = 401
    response._content = b'{"detail": "Unauthorized"}'
    with pytest.raises(errors.AuthError, match="Unauthorized"):
        success_or_raise(response)
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
