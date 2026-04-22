"""Tests for dataset API helpers."""
# pylint: disable=redefined-outer-name

from __future__ import annotations

import uuid as uuidlib
from typing import TYPE_CHECKING

import responses

from tests.conftest import get_dataset_revoke_share_permissions_url
from tests.conftest import get_datasets_endpoint

if TYPE_CHECKING:
    from spectrumx.client import Client

DRY_RUN = False
_EXPECTED_TWO_HTTP_CALLS = 2


@responses.activate
def test_delete_dataset(client: Client, responses: responses.RequestsMock) -> None:
    """Test deleting a dataset."""
    client.dry_run = DRY_RUN
    dataset_uuid = uuidlib.uuid4()
    responses.add(
        method=responses.DELETE,
        url=get_datasets_endpoint(client, dataset_id=dataset_uuid.hex),
        status=204,
    )

    result = client.datasets.delete(dataset_uuid=dataset_uuid)

    assert result is True
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "DELETE"


@responses.activate
def test_delete_dataset_bypass_share_guard(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Deleting with bypass_share_guard revokes then DELETE (no query param)."""
    client.dry_run = DRY_RUN
    dataset_uuid = uuidlib.uuid4()
    revoke_url = get_dataset_revoke_share_permissions_url(
        client, dataset_id=dataset_uuid.hex
    )
    delete_url = get_datasets_endpoint(client, dataset_id=dataset_uuid.hex)
    responses.add(
        method=responses.PUT,
        url=revoke_url,
        status=200,
        json={"message": "ok"},
    )
    responses.add(method=responses.DELETE, url=delete_url, status=204)

    result = client.datasets.delete(
        dataset_uuid=dataset_uuid,
        bypass_share_guard=True,
    )

    assert result is True
    assert len(responses.calls) == _EXPECTED_TWO_HTTP_CALLS
    assert responses.calls[0].request.method == "PUT"
    assert responses.calls[0].request.url == revoke_url
    assert responses.calls[1].request.method == "DELETE"
    assert responses.calls[1].request.url == delete_url
    assert "bypass_share_guard" not in responses.calls[1].request.url


def test_delete_dataset_dry_run(client: Client) -> None:
    """Dry run does not call the gateway."""
    client.dry_run = True
    dataset_uuid = uuidlib.uuid4()

    result = client.datasets.delete(dataset_uuid=dataset_uuid)

    assert result is True


@responses.activate
def test_revoke_dataset_share_permissions(
    client: Client, responses: responses.RequestsMock
) -> None:
    """PUT revoke-share-permissions on a dataset."""
    client.dry_run = DRY_RUN
    dataset_uuid = uuidlib.uuid4()
    revoke_url = get_dataset_revoke_share_permissions_url(
        client, dataset_id=dataset_uuid.hex
    )
    responses.add(
        method=responses.PUT,
        url=revoke_url,
        status=200,
        json={"message": "Share permissions revoked successfully"},
    )

    assert client.datasets.revoke_share_permissions(dataset_uuid) is True
    assert len(responses.calls) == 1
    assert responses.calls[0].request.method == "PUT"
    assert responses.calls[0].request.url == revoke_url


@responses.activate
def test_delete_dataset_after_revoking_share(
    client: Client, responses: responses.RequestsMock
) -> None:
    """Revoke then delete issues PUT then DELETE."""
    client.dry_run = DRY_RUN
    dataset_uuid = uuidlib.uuid4()
    revoke_url = get_dataset_revoke_share_permissions_url(
        client, dataset_id=dataset_uuid.hex
    )
    delete_url = get_datasets_endpoint(client, dataset_id=dataset_uuid.hex)
    responses.add(
        method=responses.PUT,
        url=revoke_url,
        status=200,
        json={"message": "ok"},
    )
    responses.add(method=responses.DELETE, url=delete_url, status=204)

    assert client.datasets.delete_after_revoking_share(dataset_uuid) is True
    assert len(responses.calls) == _EXPECTED_TWO_HTTP_CALLS
    assert responses.calls[0].request.method == "PUT"
    assert responses.calls[1].request.method == "DELETE"
