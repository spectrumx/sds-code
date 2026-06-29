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
    log_mock.bind.return_value.warning.assert_called_once()
    assert "capture" in log_mock.bind.return_value.warning.call_args[0][0].lower()
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
    log_mock.bind.return_value.info.assert_called_once()
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


def test_get_dry_run(client: Client) -> None:
    """Dry run for get() returns a shell Dataset without HTTP calls."""
    client.dry_run = True
    dataset_uuid = uuidlib.uuid4()
    result = client.datasets.get(dataset_uuid)
    assert result.uuid == dataset_uuid


@responses.activate
def test_get_gateway(client: Client, responses: responses.RequestsMock) -> None:
    """get() calls gateway and returns a parsed Dataset."""
    client.dry_run = False
    dataset_uuid = uuidlib.uuid4()
    mock_data = {
        "uuid": dataset_uuid.hex,
        "name": "test-dataset-from-gateway",
    }
    responses.add(
        method=responses.GET,
        url=get_datasets_endpoint(client, dataset_id=dataset_uuid.hex),
        json=mock_data,
        status=200,
    )
    result = client.datasets.get(dataset_uuid)
    assert result.uuid.hex == dataset_uuid.hex
    assert result.name == "test-dataset-from-gateway"
    assert len(responses.calls) == 1


def test_list_captures_dry_run(client: Client) -> None:
    """Dry run for list_captures() returns an empty list."""
    client.dry_run = True
    dataset_uuid = uuidlib.uuid4()
    result = client.datasets.list_captures(dataset_uuid)
    assert result == []


@responses.activate
def test_list_captures_gateway(
    client: Client, responses: responses.RequestsMock
) -> None:
    """list_captures() calls gateway and returns parsed capture payloads."""
    client.dry_run = False
    dataset_uuid = uuidlib.uuid4()
    mock_data = {
        "captures": [
            {"uuid": str(uuidlib.uuid4()), "name": "capture-1"},
        ],
    }
    responses.add(
        method=responses.GET,
        url=get_datasets_endpoint(client, dataset_id=dataset_uuid.hex),
        json=mock_data,
        status=200,
    )
    result = client.datasets.list_captures(dataset_uuid)
    assert len(result) == 1
    assert result[0]["name"] == "capture-1"
    assert len(responses.calls) == 1


def test_list_artifact_files_dry_run(client: Client) -> None:
    """Dry run for list_artifact_files() returns an empty list."""
    client.dry_run = True
    dataset_uuid = uuidlib.uuid4()
    result = client.datasets.list_artifact_files(dataset_uuid)
    assert result == []


@responses.activate
def test_list_artifact_files_gateway(
    client: Client, responses: responses.RequestsMock
) -> None:
    """list_artifact_files() calls gateway and returns parsed file payloads."""
    client.dry_run = False
    dataset_uuid = uuidlib.uuid4()
    mock_data = {
        "files": [
            {"uuid": str(uuidlib.uuid4()), "name": "file-1.txt"},
        ],
    }
    responses.add(
        method=responses.GET,
        url=get_datasets_endpoint(client, dataset_id=dataset_uuid.hex),
        json=mock_data,
        status=200,
    )
    result = client.datasets.list_artifact_files(dataset_uuid)
    assert len(result) == 1
    assert result[0]["name"] == "file-1.txt"
    assert len(responses.calls) == 1


def test_revoke_share_permissions_dry_run(client: Client) -> None:
    """Dry run for revoke_share_permissions() returns True."""
    client.dry_run = True
    dataset_uuid = uuidlib.uuid4()
    result = client.datasets.revoke_share_permissions(dataset_uuid)
    assert result is True
