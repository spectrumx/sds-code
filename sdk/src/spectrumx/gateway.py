"""Lower level module for interaction with the SpectrumX Data System."""

import os
from collections.abc import Iterator
from enum import StrEnum
from http import HTTPStatus
from pathlib import Path
from typing import Any

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
    FILE_DOWNLOAD = "/assets/files/{uuid}/download"
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

    def __init__(
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

    def get_default_payload(
        self,
        *,
        endpoint: Endpoints,
        asset_id: None | str = None,
        endpoint_args: None | dict[str, Any] = None,
    ) -> dict[str, str | dict[str, str] | bool]:
        endpoint_fmt = (
            endpoint.value.format(**endpoint_args) if endpoint_args else endpoint.value
        )
        if "{" in endpoint_fmt:
            msg = f"Endpoint '{endpoint}' has missing arguments in '{endpoint_args}'"
            raise ValueError(msg)

        assert API_TARGET_VERSION.startswith("v"), "API version must start with 'v'."
        url_path = Path(f"{API_PATH}/{API_TARGET_VERSION}/{endpoint_fmt}")
        if asset_id is not None:
            url_path /= asset_id
        url = f"{self.base_url}{url_path}/"

        is_verify = not is_test_env()
        headers = self._headers()
        return {
            "url": url,
            "headers": headers,
            "verify": is_verify,
        }

    def _request(
        self,
        method: HTTPMethods,
        endpoint: Endpoints,
        *,
        asset_id: None | str = None,
        timeout: None | int = None,
        stream: bool = False,
        endpoint_args: None | dict[str, Any] = None,
        **kwargs,
    ) -> requests.Response:
        """Makes a request to the SDS API.

        Args:
            method:     The HTTP method to use.
            endpoint:   The endpoint to target.
            asset_id:   The asset ID to target.
            timeout:    The timeout for the request.
            stream:     Streams the response if True.
            url_args:   URL arguments for the request.
            **kwargs:   Additional keyword arguments for the request e.g. URL params.
        Returns:
            The response from the request.
        """
        payload = self.get_default_payload(
            endpoint=endpoint, asset_id=asset_id, endpoint_args=endpoint_args
        )
        if self.verbose:
            log.debug(f"Gateway req: {method} {payload["url"]}")
        return requests.request(
            timeout=self.timeout if timeout is None else timeout,
            method=method,
            stream=stream,
            **payload,
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
        """Retrieves a file metadata from the SDS API. Not its contents.

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

    def get_file_contents_by_id(self, uuid: str) -> Iterator[bytes]:
        """Retrieves file contents from the SDS API.

        Args:
            uuid: The UUID of the file to retrieve as a hex string.
        Returns:
            The file contents as a byte stream.
        """
        chunk_size: int = 8192
        with self._request(
            asset_id=None,  # uuid is passed as an endpoint_args
            endpoint_args={"uuid": uuid},
            endpoint=Endpoints.FILE_DOWNLOAD,
            method=HTTPMethods.GET,
            stream=True,
        ) as stream:
            network.success_or_raise(stream, ContextException=FileError)
            for chunk in stream.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk

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
        all_chunks: bytes = b""
        with (
            file_instance.local_path.open("rb") as file_ptr,
            self._request(
                method=HTTPMethods.POST,
                endpoint=Endpoints.FILES,
                data=payload,
                stream=True,
                files={
                    "file": file_ptr,  # request.data['file'] on the server
                },
            ) as stream,
        ):
            network.success_or_raise(stream, ContextException=FileError)
            for chunk in stream.iter_content(chunk_size=8192):
                if chunk:
                    all_chunks += chunk

        return all_chunks
