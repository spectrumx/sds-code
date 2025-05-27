"""Network operations for SpectrumX SDK."""

import sys
from http import HTTPStatus

from spectrumx.utils import is_test_env

# python 3.11 backport
# Backport fixes to older versions
if sys.version_info < (3, 12):  # noqa: UP036 # pragma: no cover
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
        error_details = (
            extract_error_details_from_html(response)
            if is_test_env()
            else response.reason
        )

    error_details = str(error_details)
    log.opt(depth=1).exception(error_details)
    if status in {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN}:
        raise errors.AuthError(message=error_details)
    if status.is_client_error:
        raise ContextException(message=error_details)
    if status.is_server_error:
        raise errors.ServiceError(message=error_details)
    raise errors.SDSError(message=error_details)


def extract_error_details_from_html(response: requests.Response) -> str:
    """Extracts error details from an HTML response, focusing on specific elements."""
    try:
        from bs4 import BeautifulSoup  # pyright: ignore[reportMissingModuleSource]
    except ImportError:
        log.warning("Install 'BeautifulSoup' to have a more detailed error message.")
        return response.reason

    target_ids = ["pastebinTraceback", "summary"]
    soup = BeautifulSoup(markup=response.text, features="html.parser")
    texts: list[str] = []
    for target_id in target_ids:
        element = soup.find(id=target_id)
        if element:
            texts.append(element.get_text(strip=True))

    combined_text = "\n".join(texts)
    no_blanks = "\n".join(filter(None, combined_text.splitlines()))
    return no_blanks.strip()
