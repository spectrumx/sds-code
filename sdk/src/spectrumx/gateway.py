"""Lower level module for interaction with the SpectrumX Data System."""

import os
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
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
    CAPTURES = "/assets/captures"
    DATASETS = "/assets/datasets"
    EXPERIMENTS = "/assets/experiments"
    FILE_CONTENTS_CHECK = "/assets/utils/check_contents_exist"
    FILE_DOWNLOAD = "/assets/files/{uuid}/download"
    FILES = "/assets/files"
    SEARCH = "/search"


class HTTPMethods(StrEnum):
    """Contains the HTTP methods for the SDS Gateway API."""

    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"
    PUT = "PUT"


@dataclass
class FileContentsCheck:
    file_contents_exist_for_user: bool
    file_exists_in_tree: bool
    user_mutable_attributes_differ: bool
    asset_id: uuid.UUID | None = None


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
        endpoint_args: None | dict[str, Any] = None,
        stream: bool = False,
        timeout: None | int = None,
        verbose: bool = False,
        **kwargs,
    ) -> requests.Response:
        """Makes a request to the SDS API.

        Args:
            method:         The HTTP method to use.
            endpoint:       The endpoint to target.
            asset_id:       The asset ID to target.
            endpoint_args:  Arguments part of the endpoint e.g.: /path/{arg}/subpath.
            stream:         Streams the response if True.
            timeout:        The timeout for the request.
            verbose:        Whether to log the request.
            **kwargs:       Additional arguments for the request e.g. URL params.
        Returns:
            The response from the request.
        """
        payload = self.get_default_payload(
            endpoint=endpoint, asset_id=asset_id, endpoint_args=endpoint_args
        )
        if self.verbose or verbose:
            debug_str = f"GWY req: {method} {payload['url']}"
            if "params" in kwargs:
                debug_str += f" params={kwargs['params']}"
            if "asset_id" in kwargs:
                debug_str += f" asset_id={kwargs['asset_id']}"
            log.debug(debug_str)
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

    def authenticate(self, *, verbose: bool = False) -> None:
        """Authenticates the client with the SDS API."""
        assert self._api_key is not None, "API key is required for authentication."
        response = self._request(
            method=HTTPMethods.GET, endpoint=Endpoints.AUTH, verbose=verbose
        )
        status = HTTPStatus(response.status_code)
        log.debug(f"Authentication response: {status}")
        if status.is_success:
            return
        msg = f"Authentication failed: {response.text}"
        raise AuthError(msg)

    # ============
    # FILE METHODS

    def get_file_by_id(self, uuid: str, *, verbose: bool = False) -> bytes:
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
            verbose=verbose,
        )
        network.success_or_raise(response, ContextException=FileError)
        return response.content

    def get_file_contents_by_id(
        self, uuid: str, *, verbose: bool = False
    ) -> Iterator[bytes]:
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
            verbose=verbose,
        ) as stream:
            network.success_or_raise(stream, ContextException=FileError)
            for chunk in stream.iter_content(chunk_size=chunk_size):
                if chunk:
                    yield chunk

    def list_files(
        self,
        *,
        sds_path: Path,
        page: int = 1,
        page_size: int = 30,
        verbose: bool = False,
    ) -> bytes:
        """Lists files from the SDS API.

        Returns:
            The response content from SDS Gateway.
        """
        response = self._request(
            method=HTTPMethods.GET,
            endpoint=Endpoints.FILES,
            params={
                "page": page,
                "page_size": page_size,
                "path": str(sds_path),
            },
            verbose=verbose,
        )
        network.success_or_raise(response, ContextException=FileError)
        return response.content

    def check_file_contents_exist(
        self,
        file_instance: File,
        *,
        verbose: bool = False,
    ) -> FileContentsCheck:
        """Checks if the file contents exist on the SDS API.

        Args:
            uuid: The UUID of the file to check as a hex string.
        Returns:
            FileContentsCheck
        """
        payload = {
            "directory": str(file_instance.directory),
            "media_type": file_instance.media_type,
            "name": file_instance.name,
            "sum_blake3": file_instance.compute_sum_blake3(),
            "permissions": file_instance.permissions,
        }
        response = self._request(
            method=HTTPMethods.POST,
            endpoint=Endpoints.FILE_CONTENTS_CHECK,
            data=payload,
            verbose=verbose,
        )
        network.success_or_raise(response=response, ContextException=FileError)
        return FileContentsCheck(**response.json())

    def upload_new_file(self, file_instance: File, *, verbose: bool = False) -> bytes:
        """Uploads a local file to the SDS API.

        Uploads file contents and metadata.

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
                verbose=verbose,
            ) as stream,
        ):
            network.success_or_raise(response=stream, ContextException=FileError)
            for chunk in stream.iter_content(chunk_size=8192):
                if chunk:
                    all_chunks += chunk

        return all_chunks

    def upload_new_file_metadata_only(
        self,
        file_instance: File,
        sibling_uuid: uuid.UUID,
        *,
        verbose: bool = False,
    ) -> bytes:
        """UPLOADS a new file to the SDS API without its contents.

        Useful when a sibling file with the same content
            exists, so its upload can be skipped.

        Args:
            file_instance: The file to upload, as a models.File instance.
            sibling_uuid:  The UUID of the sibling file.
            verbose:       Whether to log the request.
        Returns:
            The response content from SDS Gateway.
        """
        payload = {
            "directory": str(file_instance.directory),
            "media_type": file_instance.media_type,
            "name": file_instance.name,
            "permissions": file_instance.permissions,
            "sum_blake3": file_instance.compute_sum_blake3(),
            "sibling_uuid": sibling_uuid.hex,
        }
        response = self._request(
            method=HTTPMethods.POST,
            endpoint=Endpoints.FILES,
            data=payload,
            verbose=verbose,
        )
        network.success_or_raise(response=response, ContextException=FileError)
        return response.content

    def update_existing_file_metadata(
        self, file_instance: File, *, verbose: bool = False
    ) -> bytes:
        """UPDATES an existing file's metadata to the SDS API.

        Args:
            file_instance:  The file to update, as a models.File instance.
            verbose:        Whether to log the request.
        Returns:
            The response content from SDS Gateway.
        """
        payload = {
            "directory": str(file_instance.directory),
            "media_type": file_instance.media_type,
            "name": file_instance.name,
            "permissions": file_instance.permissions,
            "sum_blake3": file_instance.compute_sum_blake3(),
        }
        assert file_instance.uuid is not None, (
            "File UUID is required for metadata update."
        )
        response = self._request(
            asset_id=file_instance.uuid.hex,
            data=payload,
            endpoint=Endpoints.FILES,
            method=HTTPMethods.PUT,
            verbose=verbose,
        )
        network.success_or_raise(response=response, ContextException=FileError)
        return response.content

    # ===============
    # CAPTURE METHODS
