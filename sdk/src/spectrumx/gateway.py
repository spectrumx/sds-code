"""Lower level module for interaction with the SpectrumX Data System."""

import os
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path

import requests
from loguru import logger as log

from .errors import AuthError
from .errors import FileError
from .models import File
from .ops import network
from .utils import log_user_warning

API_PATH: str = "/api/"
API_TARGET_VERSION: str = "v1"


def is_test_env() -> bool:
    """Returns whether the current environment is a test environment."""
    env_var = os.getenv("PYTEST_CURRENT_TEST", default=None)
    return env_var is not None


class Endpoints(StrEnum):
    """Contains the endpoints for the SDS Gateway API."""

    AUTH = "/auth"
    FILES = "/assets/files"
    CAPTURES = "/assets/captures"
    DATASETS = "/assets/datasets"
    EXPERIMENTS = "/assets/experiments"
    SEARCH = "/search"


class HTTPMethods(StrEnum):
    """Contains the HTTP methods for the SDS Gateway API."""

    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"
    PUT = "PUT"


class GatewayClient:
    """Communicates with the SDS API."""

    host: str
    port: int
    protocol: str
    timeout: int
    verbose: bool = False

    _api_key: str

    def __init__(  # noqa: PLR0913
        self,
        *,
        host: str,
        api_key: str,
        port: int | None = None,
        protocol: str | None = None,
        timeout: int = 30,
        verbose: bool = False,
    ) -> None:
        self.host = host

        fallback_protocol = "http" if host == "localhost" else "https"
        self.protocol = protocol if protocol is not None else fallback_protocol

        fallback_port = 80 if self.protocol == "http" else 443
        self.port = port if port is not None else fallback_port

        self.timeout = timeout
        self.verbose = verbose
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        """Returns the headers for the request."""
        if not self._api_key:
            msg = "API key not set. Check your env config."
            log_user_warning(msg)
        return {
            "Authorization": f"Api-Key: {self._api_key}",
        }

    def _request(
        self,
        method: HTTPMethods,
        endpoint: Endpoints,
        asset_id: None | str = None,
        timeout: None | int = None,
        **kwargs,
    ) -> requests.Response:
        """Makes a request to the SDS API.

        Args:
            method:     The HTTP method to use.
            endpoint:   The endpoint to target.
            asset_id:   The asset ID to target.
            timeout:    The timeout for the request.
            **kwargs:   Additional keyword arguments for the request e.g. URL params.
        Returns:
            The response from the request.
        """
        assert API_TARGET_VERSION.startswith("v"), "API version must start with 'v'."
        url_path = Path(f"{API_PATH}/{API_TARGET_VERSION}/{endpoint}")
        if asset_id is not None:
            url_path /= asset_id
        url = f"{self.base_url}{url_path}/"
        timeout = self.timeout if timeout is None else timeout
        is_verify = not is_test_env()
        headers = self._headers()
        if self.verbose:
            log.debug(f"Gateway req: {method} {url}")
        return requests.request(
            method=method,
            url=url,
            headers=headers,
            timeout=timeout,
            verify=is_verify,
            **kwargs,
        )

    @property
    def base_url(self) -> str:
        """Returns the base URL for the SDS API."""
        return f"{self.protocol}://{self.host}:{self.port}"

    @property
    def base_url_no_port(self) -> str:
        """Returns the base URL for the SDS API, without the port."""
        return f"{self.protocol}://{self.host}"

    def authenticate(self) -> None:
        """Authenticates the client with the SDS API."""
        assert self._api_key is not None, "API key is required for authentication."
        response = self._request(method=HTTPMethods.GET, endpoint=Endpoints.AUTH)
        status = HTTPStatus(response.status_code)
        log.debug(f"Authentication response: {status}")
        if status.is_success:
            return
        msg = f"Authentication failed: {response.text}"
        raise AuthError(msg)

    def get_file_by_id(self, uuid: str) -> bytes:
        """Retrieves a file from the SDS API.

        Args:
            uuid: The UUID of the file to retrieve as a hex string.
        Returns:
            The file content.
        """
        response = self._request(
            method=HTTPMethods.GET,
            endpoint=Endpoints.FILES,
            asset_id=uuid,
        )
        network.success_or_raise(response, FileError)
        return response.content

    def upload_file(self, file_instance: File) -> bytes:
        """Uploads a local file to the SDS API.

        Args:
            file_instance: The file to upload, as a models.File instance.
        """
        if file_instance.local_path is None:
            msg = "Attempting to upload a remote file. Download it first."
            raise FileError(msg)

        payload = {
            "directory": str(file_instance.directory),
            "media_type": file_instance.media_type,
        }
        with file_instance.local_path.open("rb") as file_ptr:
            response = self._request(
                method=HTTPMethods.POST,
                endpoint=Endpoints.FILES,
                data=payload,
                files={
                    "file": file_ptr,  # request.data['file']
                },
            )
            network.success_or_raise(response, FileError)
            return response.content
