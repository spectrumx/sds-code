"""
Tests for the high-level usage of SpectrumX client.
"""

# pylint: disable=redefined-outer-name
import uuid as uuidlib

import pytest
from responses import RequestsMock

from spectrumx import Client
from spectrumx.errors import AuthError
from spectrumx.gateway import Endpoints


@pytest.fixture
def client() -> Client:
    """Fixture to create a Client instance for testing."""
    return Client(host="sds.crc.nd.edu")


def test_authentication_200_succeeds(client: Client, responses: RequestsMock) -> None:
    """Given a successful auth response, the client must be authenticated."""
    responses.get(
        client.base_url + "/auth",
        body="{}",
        status=200,
        content_type="application/json",
    )
    client.authenticate()
    assert client.is_authenticated


def test_authentication_401_fails(client: Client, responses: RequestsMock) -> None:
    """Given a failed auth response, the client must raise AuthError."""
    responses.get(
        client.base_url + "/auth",
        body="{}",
        status=401,
        content_type="application/json",
    )
    with pytest.raises(AuthError):
        client.authenticate()


def test_get_file_by_id(client: Client, responses) -> None:
    """Given a file ID, the client must return the file."""
    uuid = uuidlib.uuid4()
    url: str = client.base_url + Endpoints.FILES
    url += f"?uuid={uuid.hex}"
    responses.get(
        url=url,
        status=200,
        json={
            "created_at": "2021-10-01T12:00:00",
            "directory": "/my/files/are/here/",
            "expiration_date": "2021-10-01",
            "media_type": "text/plain",
            "name": "file.txt",
            "permissions": "rw-rw-r--",
            "size": 321,
            "updated_at": "2021-10-01T12:00:00",
            "uuid": uuid.hex,
        },
    )
    file_sample = client.get_file(file_id=uuid.hex)
    assert file_sample.uuid == uuid
