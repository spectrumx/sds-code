"""Integration tests with SDS for testing authentication.

Use the integration_client fixture for these tests.
"""

import pytest
from responses import RequestsMock
from spectrumx import Client
from spectrumx.errors import AuthError


@pytest.mark.withoutresponses
def test_authentication_200_succeeds(
    integration_client: Client, responses: RequestsMock
) -> None:
    """Given a successful auth response, the client must be authenticated."""

    # setting up
    responses.reset()
    urls_to_bypass_responses = [
        "https://sds.crc.nd.edu:443/api/v1/auth",
        "http://localhost:80/api/v1/auth",
    ]
    for url in urls_to_bypass_responses:
        responses.add_passthru(prefix=url)

    # auth test
    try:
        integration_client.authenticate()
        assert integration_client.is_authenticated
    except AuthError as err:
        msg = (
            "Authentication failed: make sure the api key in `integration.env` "
            "matches the server's: you need to set it manually. Error:"
            f" {err}"
        )
        pytest.fail(msg)

    # teardown
    responses.reset()
