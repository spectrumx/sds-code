"""Unit tests for shared federation Redis channel and index write helpers."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from uuid import UUID

import pytest
from sds_opensearch_query.index_write import FED_DATASETS_INDEX
from sds_opensearch_query.index_write import federated_doc_id
from sds_opensearch_query.index_write import index_federated_document
from sds_opensearch_query.redis_channel import federation_events_channel
from sds_opensearch_query.redis_channel import resolve_federation_events_channel


def test_federation_events_channel_uses_site_name() -> None:
    assert federation_events_channel("crc") == "federation:events:crc"


def test_federation_events_channel_rejects_blank_site() -> None:
    with pytest.raises(ValueError, match="site_name"):
        federation_events_channel("  ")


def test_resolve_prefers_channel_override() -> None:
    assert (
        resolve_federation_events_channel(
            site_name="crc",
            channel_override="custom:channel",
            gateway_site_name="other",
        )
        == "custom:channel"
    )


def test_resolve_env_override_alias() -> None:
    assert (
        resolve_federation_events_channel(
            site_name="crc",
            env_override="custom:channel",
        )
        == "custom:channel"
    )


def test_resolve_prefers_gateway_site_name_over_toml() -> None:
    assert (
        resolve_federation_events_channel(
            site_name="toml-name",
            gateway_site_name="gateway-name",
        )
        == "federation:events:gateway-name"
    )


def test_resolve_derives_from_site_when_no_override() -> None:
    assert (
        resolve_federation_events_channel(site_name="haystack")
        == "federation:events:haystack"
    )


def test_resolve_empty_when_unconfigured() -> None:
    assert resolve_federation_events_channel() == ""


def test_federated_doc_id_format() -> None:
    uid = UUID("12345678-1234-5678-1234-567812345678")
    assert federated_doc_id("sds.crc.nd.edu", uid) == (
        "sds.crc.nd.edu:12345678-1234-5678-1234-567812345678"
    )


class _RecordingClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def index(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_index_federated_document_stamps_event_at() -> None:
    client = _RecordingClient()
    uid = UUID("12345678-1234-5678-1234-567812345678")
    event_at = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)

    doc_id = index_federated_document(
        client,  # type: ignore[arg-type]
        index_name=FED_DATASETS_INDEX,
        site_name="sds.crc.nd.edu",
        uuid=uid,
        body={"name": "demo", "site_name": "sds.crc.nd.edu"},
        event_at=event_at,
    )

    assert doc_id == federated_doc_id("sds.crc.nd.edu", uid)
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["index"] == FED_DATASETS_INDEX
    assert call["id"] == doc_id
    assert call["body"]["federation_event_at"] == event_at.isoformat()
    assert call["body"]["name"] == "demo"
    assert call["refresh"] == "wait_for"
