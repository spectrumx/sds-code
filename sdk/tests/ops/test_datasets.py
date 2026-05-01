"""Tests for dataset API helpers."""
# pylint: disable=redefined-outer-name

from __future__ import annotations

import uuid as uuidlib
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
import responses
from spectrumx.api.datasets import DatasetAPI
from spectrumx.errors import DatasetError
from spectrumx.gateway import GatewayClient

from tests.conftest import get_dataset_revoke_share_permissions_url
from tests.conftest import get_datasets_endpoint

if TYPE_CHECKING:
    from spectrumx.client import Client

DRY_RUN = False

_EMPTY_MANIFEST = b'{"count": 0, "next": null, "previous": null, "results": []}'


def _dataset_api() -> DatasetAPI:
    return DatasetAPI(
        gateway=GatewayClient(host="example.invalid", api_key="test-key"),
        dry_run=False,
    )


def test_get_files_artifacts_only_forwards_to_gateway() -> None:
    """artifacts_only is passed through to the gateway list call."""
    api = _dataset_api()
    ds = uuidlib.uuid4()
    gw = api.gateway
    with patch.object(gw, "get_dataset_files", return_value=_EMPTY_MANIFEST) as m:
        paginator = api.get_files(ds, artifacts_only=True)
        assert len(paginator) == 0
    m.assert_called_once()
    assert m.call_args.kwargs["artifacts_only"] is True
    assert m.call_args.kwargs["dataset_uuid"] == ds


def test_get_files_artifacts_only_clears_capture_uuids_and_warns() -> None:
    """Non-empty capture_uuids with artifacts_only logs a warning and omits captures."""
    api = _dataset_api()
    ds = uuidlib.uuid4()
    cap = uuidlib.uuid4()
    gw = api.gateway
    with (
        patch.object(gw, "get_dataset_files", return_value=_EMPTY_MANIFEST) as mock_get,
        patch("spectrumx.api.datasets.log") as log_mock,
    ):
        paginator = api.get_files(ds, capture_uuids=(cap,), artifacts_only=True)
        assert len(paginator) == 0
    log_mock.warning.assert_called_once()
    assert "capture" in log_mock.warning.call_args[0][0].lower()
    kw = mock_get.call_args.kwargs
    assert kw.get("capture_uuids") in (None, ())
    assert kw["artifacts_only"] is True


def test_get_files_artifacts_only_with_top_level_dirs_logs_info() -> None:
    """top_level_dirs with artifacts_only still forwards dirs and logs info."""
    api = _dataset_api()
    ds = uuidlib.uuid4()
    gw = api.gateway
    with (
        patch.object(gw, "get_dataset_files", return_value=_EMPTY_MANIFEST) as mock_get,
        patch("spectrumx.api.datasets.log") as log_mock,
    ):
        paginator = api.get_files(
            ds,
            top_level_dirs=("/pytest/root",),
            artifacts_only=True,
        )
        assert len(paginator) == 0
    log_mock.info.assert_called_once()
    kw = mock_get.call_args.kwargs
    assert kw["top_level_dirs"] == ("/pytest/root",)
    assert kw["artifacts_only"] is True


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
def test_delete_dataset_raises_when_gateway_rejects_shared(
    client: Client, responses: responses.RequestsMock
) -> None:
    """DELETE fails with 400 when the dataset is still shared (gateway message)."""
    client.dry_run = DRY_RUN
    dataset_uuid = uuidlib.uuid4()
    delete_url = get_datasets_endpoint(client, dataset_id=dataset_uuid.hex)
    err_msg = "Cannot delete dataset: revoke share permissions first."
    responses.add(
        method=responses.DELETE,
        url=delete_url,
        status=400,
        json={"detail": err_msg},
    )
    with pytest.raises(DatasetError) as exc_info:
        client.datasets.delete(dataset_uuid=dataset_uuid)
    assert err_msg in str(exc_info.value)
    assert len(responses.calls) == 1


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
