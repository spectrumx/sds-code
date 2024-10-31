"""Network operations for SpectrumX SDK."""

from http import HTTPStatus

import requests

from spectrumx import errors


def success_or_raise(
    response: requests.Response,
    ContextException: type[errors.SDSError],  # noqa: N803
) -> None:
    """Checks a response is successful, raising a contextual error if not."""
    status = HTTPStatus(response.status_code)
    if status.is_success:
        return
    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise errors.AuthError(message=response.text)
    if status.is_client_error:
        raise ContextException(message=response.text)
    if status.is_server_error:
        raise errors.ServiceError(message=response.text)
    raise errors.SDSError(message=response.text)
