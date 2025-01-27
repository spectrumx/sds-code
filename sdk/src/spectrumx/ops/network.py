"""Network operations for SpectrumX SDK."""

from http import HTTPStatus

import requests
from loguru import logger as log

from spectrumx import errors


def success_or_raise(
    response: requests.Response,
    ContextException: type[errors.SDSError] = errors.SDSError,  # noqa: N803
) -> None:
    """Checks a response is successful, raising a contextual error if not."""
    status = HTTPStatus(response.status_code)
    if status.is_success:
        return

    log.info(response)
    try:
        error_json = response.json()
        error_details = error_json.get("detail", error_json)
    except requests.exceptions.JSONDecodeError:
        error_details = response.content

    error_details = str(error_details)
    log.opt(depth=1).exception(error_details)
    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise errors.AuthError(message=error_details)
    if status.is_client_error:
        raise ContextException(message=error_details)
    if status.is_server_error:
        raise errors.ServiceError(message=error_details)
    raise errors.SDSError(message=error_details)
