"""Lower level module for interaction with the SpectrumX Data System."""

from enum import StrEnum
from http import HTTPStatus
from pathlib import Path

import requests

from spectrumx import ops
from spectrumx.models import File

from .errors import AuthError
from .errors import FileError

API_PATH: str = "/api/"
API_TARGET_VERSION: str = "v1"


class Endpoints(StrEnum):
    """Contains the endpoints for the SDS Gateway API."""

    AUTH = "/auth"  # GET; simple "200 OK" if the API key is valid
    FILES = "/assets/files"  # GET, POST, DELETE
    CAPTURES = "/assets/captures"  # GET, POST, DELETE, PUT
    DATASETS = "/assets/datasets"  # GET, POST, DELETE, PUT
    EXPERIMENTS = "/assets/experiments"  # GET, POST, DELETE, PUT
    SEARCH = "/search"  # POST (needs to send a JSON payload)


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

    _api_key: str

    def __init__(
        self,
        host: str,
        api_key: str,
        port: int = 443,
        protocol: str = "https",
        timeout: int = 30,
    ) -> None:
        self.host = host
        self.port = port
        self.protocol = protocol
        self.timeout = timeout
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        """Returns the headers for the request."""
        return {
            "Authorization": f"Api-Key {self._api_key}",
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
        url_path = Path(API_PATH) / API_TARGET_VERSION / endpoint
        if asset_id is not None:
            url_path /= asset_id
        url = f"{self.base_url}{url_path}"
        if timeout is None:
            timeout = self.timeout
        return requests.request(
            method=method,
            url=url,
            headers=self._headers(),
            timeout=timeout,
            **kwargs,
        )

    @property
    def base_url(self) -> str:
        """Returns the base URL for the SDS API."""
        return f"{self.protocol}://{self.host}:{self.port}"

    def authenticate(self) -> None:
        """Authenticates the client with the SDS API."""
        assert self._api_key is not None, "API key is required for authentication."
        response = self._request(method=HTTPMethods.GET, endpoint=Endpoints.AUTH)
        status = HTTPStatus(response.status_code)
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
        ops.network.success_or_raise(response, FileError)
        return response.content

    def upload_file(self, file_instance: File) -> bytes:
        """Uploads a local file to the SDS API.

        Args:
            file_instance: The file to upload, as a models.File instance.
        """
        if file_instance.local_path is None:
            msg = "Attempting to upload a remote file. Download it first."
            raise FileError(msg)
        with file_instance.local_path.open("rb") as file_ptr:
            response = self._request(
                method=HTTPMethods.POST,
                endpoint=Endpoints.FILES,
                files={"file": file_ptr},
            )
            ops.network.success_or_raise(response, FileError)
            return response.content
