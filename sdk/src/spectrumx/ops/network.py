"""Network operations for SpectrumX SDK."""

import sys
from http import HTTPStatus

if sys.version_info < (3, 12):  # noqa: UP036 # Backport fixes to older versions
    HTTPStatus.is_informational = property(lambda s: 100 <= s <= 199)  # noqa: PLR2004
    HTTPStatus.is_success = property(lambda s: 200 <= s <= 299)  # noqa: PLR2004
    HTTPStatus.is_redirection = property(lambda s: 300 <= s <= 399)  # noqa: PLR2004
    HTTPStatus.is_client_error = property(lambda s: 400 <= s <= 499)  # noqa: PLR2004
    HTTPStatus.is_server_error = property(lambda s: 500 <= s <= 599)  # noqa: PLR2004


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
