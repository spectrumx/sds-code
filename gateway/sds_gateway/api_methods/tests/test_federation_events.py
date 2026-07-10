"""Tests for federation Redis event channel naming and publish."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import MagicMock
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.test import TestCase
from django.test import override_settings

from sds_gateway.api_methods.federation.events import publish_federation_event
from sds_gateway.api_methods.federation.redis_channel import (
    resolve_federation_events_channel,
)
from sds_gateway.api_methods.federation.signals import federation_dataset_changed
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.tests.factories import DatasetFactory

pytestmark = pytest.mark.django_db


@contextmanager
def _federation_on_commit():
    with TestCase.captureOnCommitCallbacks(execute=True):
        yield


class TestResolveFederationEventsChannel:
    def test_site_prefixed_when_site_name_set(self) -> None:
        assert (
            resolve_federation_events_channel(site_name="crc")
            == "federation:events:crc"
        )

    def test_override_wins_over_site_name(self) -> None:
        assert (
            resolve_federation_events_channel(
                site_name="crc",
                channel_override="federation:events:custom",
            )
            == "federation:events:custom"
        )

    def test_empty_when_no_site_and_no_override(self) -> None:
        assert resolve_federation_events_channel() == ""


class TestPublishFederationEvent:
    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_OPERATIONAL_OVERRIDE=True,
        FEDERATION_EVENTS_CHANNEL="federation:events:crc",
    )
    @patch("sds_gateway.api_methods.federation.events.get_redis_client")
    def test_publish_uses_configured_channel(
        self,
        mock_get_redis: MagicMock,
    ) -> None:
        mock_client = MagicMock()
        mock_get_redis.return_value = mock_client
        item_uuid = uuid4()

        publish_federation_event(
            item_type=ItemType.DATASET,
            uuid=item_uuid,
        )

        mock_client.publish.assert_called_once()
        channel, payload_raw = mock_client.publish.call_args[0]
        assert channel == "federation:events:crc"
        payload = json.loads(payload_raw)
        assert payload["item_type"] == ItemType.DATASET.value
        assert payload["uuid"] == str(item_uuid)

    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_OPERATIONAL_OVERRIDE=False,
        FEDERATION_EVENTS_CHANNEL="federation:events:crc",
    )
    @patch("sds_gateway.api_methods.federation.events.get_redis_client")
    def test_skips_publish_when_not_operational(
        self,
        mock_get_redis: MagicMock,
    ) -> None:
        publish_federation_event(
            item_type=ItemType.CAPTURE,
            uuid=uuid4(),
        )
        mock_get_redis.assert_not_called()


class TestFederationSignals:
    @override_settings(
        FEDERATION_ENABLED=True,
        FEDERATION_SITE_NAME="crc",
        FEDERATION_OPERATIONAL_OVERRIDE=True,
        FEDERATION_EVENTS_CHANNEL="federation:events:crc",
    )
    @patch("sds_gateway.api_methods.federation.reindex.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.reindex.LocalFederatedIndexer")
    @patch(
        "sds_gateway.api_methods.federation.reindex.get_opensearch_client",
        new=MagicMock(),
    )
    def test_dataset_post_save_indexes_when_published(
        self,
        mock_indexer_cls: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(
            status=DatasetStatus.FINAL,
            is_public=True,
        )
        with _federation_on_commit():
            federation_dataset_changed(
                sender=Dataset,
                instance=dataset,
                created=False,
            )

        mock_indexer.apply_local_event.assert_called_once()
        call = mock_indexer.apply_local_event.call_args.kwargs
        assert call["site_name"] == "crc"
        assert call["item_type"] == ItemType.DATASET
        assert call["uuid"] == dataset.uuid
        mock_publish.assert_called_once_with(
            item_type=ItemType.DATASET,
            uuid=dataset.uuid,
            timestamp=dataset.updated_at,
        )
