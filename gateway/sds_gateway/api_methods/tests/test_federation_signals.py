"""Tests for federation signal orchestration."""

from __future__ import annotations

from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.test import override_settings

from sds_gateway.api_methods.federation.signals import federation_capture_changed
from sds_gateway.api_methods.federation.signals import federation_dataset_changed
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.tests.factories import CaptureFactory
from sds_gateway.api_methods.tests.factories import DatasetFactory

pytestmark = pytest.mark.django_db


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
)
class TestFederationDatasetSignals(TestCase):
    @patch("sds_gateway.api_methods.federation.signals.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.signals.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.signals.get_opensearch_client")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=False)
    def test_published_dataset_upserts_and_syncs_captures(
        self,
        _mock_exists: MagicMock,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        federation_dataset_changed(
            sender=Dataset,
            instance=dataset,
            created=False,
        )

        assert mock_indexer.apply_local_event.call_count == 2
        item_types = {
            c.kwargs["item_type"]
            for c in mock_indexer.apply_local_event.call_args_list
        }
        assert item_types == {ItemType.DATASET, ItemType.CAPTURE}
        assert mock_publish.call_count == 2

    @patch("sds_gateway.api_methods.federation.signals.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.signals.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.signals.get_opensearch_client")
    @patch(
        "sds_gateway.api_methods.federation.signals.fed_doc_exists",
        return_value=True,
    )
    @patch(
        "sds_gateway.api_methods.federation.signals.fed_doc_is_tombstoned",
        return_value=False,
    )
    def test_deleted_dataset_tombstones_when_doc_exists(
        self,
        _mock_tombstone: MagicMock,
        _mock_exists: MagicMock,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=True,
        )

        federation_dataset_changed(
            sender=Dataset,
            instance=dataset,
            created=False,
        )

        mock_indexer.apply_local_event.assert_called()
        deleted_calls = [
            c
            for c in mock_indexer.apply_local_event.call_args_list
            if c.kwargs.get("event_type") == "deleted"
        ]
        assert deleted_calls

    @patch("sds_gateway.api_methods.federation.signals._upsert_federated")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=False)
    def test_draft_dataset_skips_federation(
        self,
        _mock_exists: MagicMock,
        mock_upsert: MagicMock,
    ) -> None:
        dataset = DatasetFactory(status=DatasetStatus.DRAFT, is_public=False)
        federation_dataset_changed(sender=Dataset, instance=dataset, created=True)
        mock_upsert.assert_not_called()

    @patch("sds_gateway.api_methods.federation.signals._tombstone_federated_if_exists")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=True)
    @patch(
        "sds_gateway.api_methods.federation.signals.fed_doc_is_tombstoned",
        return_value=False,
    )
    def test_deleted_dataset_skips_capture_tombstone_when_on_other_published(
        self,
        _mock_tombstone_flag: MagicMock,
        _mock_exists: MagicMock,
        mock_tombstone: MagicMock,
    ) -> None:
        dataset_a = DatasetFactory(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=True,
        )
        dataset_b = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset_a, dataset_b)

        federation_dataset_changed(
            sender=Dataset,
            instance=dataset_a,
            created=False,
        )

        tombstone_calls = [
            c for c in mock_tombstone.call_args_list if c.args[1] == ItemType.DATASET
        ]
        assert len(tombstone_calls) == 1
        capture_tombstones = [
            c for c in mock_tombstone.call_args_list if c.args[1] == ItemType.CAPTURE
        ]
        assert not capture_tombstones

    @patch("sds_gateway.api_methods.federation.signals._tombstone_federated_if_exists")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=True)
    @patch(
        "sds_gateway.api_methods.federation.signals.fed_doc_is_tombstoned",
        return_value=False,
    )
    def test_deleted_dataset_tombstones_orphan_capture(
        self,
        _mock_tombstone_flag: MagicMock,
        _mock_exists: MagicMock,
        mock_tombstone: MagicMock,
    ) -> None:
        dataset = DatasetFactory(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=True,
        )
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        federation_dataset_changed(
            sender=Dataset,
            instance=dataset,
            created=False,
        )

        assert mock_tombstone.call_count == 2


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
)
class TestFederationCaptureSignals(TestCase):
    @patch("sds_gateway.api_methods.federation.signals.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.signals.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.signals.get_opensearch_client")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=False)
    def test_capture_on_published_dataset_upserts(
        self,
        _mock_exists: MagicMock,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        federation_capture_changed(sender=Capture, instance=capture)

        mock_indexer.apply_local_event.assert_called_once()
        assert (
            mock_indexer.apply_local_event.call_args.kwargs["item_type"]
            == ItemType.CAPTURE
        )
        mock_publish.assert_called_once()

    @patch("sds_gateway.api_methods.federation.signals._upsert_federated")
    def test_capture_on_draft_dataset_skips_upsert(
        self,
        mock_upsert: MagicMock,
    ) -> None:
        dataset = DatasetFactory(status=DatasetStatus.DRAFT, is_public=False)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)
        federation_capture_changed(sender=Capture, instance=capture)
        mock_upsert.assert_not_called()

    @patch("sds_gateway.api_methods.federation.signals._tombstone_federated_if_exists")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=True)
    @patch(
        "sds_gateway.api_methods.federation.signals.fed_doc_is_tombstoned",
        return_value=False,
    )
    def test_deleted_capture_tombstones_when_doc_exists(
        self,
        _mock_tombstone_flag: MagicMock,
        _mock_exists: MagicMock,
        mock_tombstone: MagicMock,
    ) -> None:
        capture = CaptureFactory(is_deleted=True)
        federation_capture_changed(sender=Capture, instance=capture)
        mock_tombstone.assert_called_once_with(capture, ItemType.CAPTURE)

    @patch("sds_gateway.api_methods.federation.signals._tombstone_federated_if_exists")
    @patch("sds_gateway.api_methods.federation.signals.fed_doc_exists", return_value=True)
    @patch(
        "sds_gateway.api_methods.federation.signals.fed_doc_is_tombstoned",
        return_value=True,
    )
    def test_stale_deleted_capture_ignored(
        self,
        _mock_tombstone_flag: MagicMock,
        _mock_exists: MagicMock,
        mock_tombstone: MagicMock,
    ) -> None:
        capture = CaptureFactory(is_deleted=True)
        federation_capture_changed(sender=Capture, instance=capture)
        mock_tombstone.assert_not_called()
