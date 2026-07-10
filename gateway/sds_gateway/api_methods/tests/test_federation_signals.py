"""Tests for federation signal orchestration."""

from __future__ import annotations

from contextlib import contextmanager
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
from sds_gateway.api_methods.utils.asset_access_control import (
    disconnect_captures_from_dataset,
)

pytestmark = pytest.mark.django_db


@contextmanager
def _federation_on_commit():
    with TestCase.captureOnCommitCallbacks(execute=True):
        yield


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
)
class TestFederationDatasetSignals(TestCase):
    @patch("sds_gateway.api_methods.federation.reindex.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.reindex.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.reindex.get_opensearch_client")
    def test_published_dataset_upserts_and_syncs_captures(
        self,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        with _federation_on_commit():
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

    @patch("sds_gateway.api_methods.federation.reindex.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.reindex.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.reindex.get_opensearch_client")
    @patch(
        "sds_gateway.api_methods.federation.reindex.get_federated_export_doc_by_uuid",
        return_value={"is_deleted": False},
    )
    @patch(
        "sds_gateway.api_methods.federation.reindex.fed_doc_exists",
        return_value=True,
    )
    def test_deleted_dataset_reindexes_full_body(
        self,
        _mock_exists: MagicMock,
        _mock_doc: MagicMock,
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

        with _federation_on_commit():
            federation_dataset_changed(
                sender=Dataset,
                instance=dataset,
                created=False,
            )

        mock_indexer.apply_local_event.assert_called_once()
        call = mock_indexer.apply_local_event.call_args.kwargs
        assert call["item_type"] == ItemType.DATASET
        assert call["body"]["is_deleted"] is True
        mock_publish.assert_called_once_with(
            item_type=ItemType.DATASET,
            uuid=dataset.uuid,
            timestamp=dataset.updated_at,
        )

    @patch("sds_gateway.api_methods.federation.reindex.reindex_federated_asset")
    def test_draft_dataset_skips_federation(
        self,
        mock_reindex: MagicMock,
    ) -> None:
        dataset = DatasetFactory(status=DatasetStatus.DRAFT, is_public=False)
        with _federation_on_commit():
            federation_dataset_changed(sender=Dataset, instance=dataset, created=True)
        mock_reindex.assert_not_called()

    @patch("sds_gateway.api_methods.federation.reindex.reindex_federated_asset")
    @patch(
        "sds_gateway.api_methods.federation.reindex.get_federated_export_doc_by_uuid",
        return_value={"is_deleted": True},
    )
    @patch(
        "sds_gateway.api_methods.federation.reindex.fed_doc_exists",
        return_value=True,
    )
    def test_deleted_dataset_skips_when_fed_doc_already_deleted(
        self,
        _mock_exists: MagicMock,
        _mock_doc: MagicMock,
        mock_reindex: MagicMock,
    ) -> None:
        dataset = DatasetFactory(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=True,
        )
        with _federation_on_commit():
            federation_dataset_changed(sender=Dataset, instance=dataset, created=False)
        mock_reindex.assert_not_called()


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
)
class TestFederationCaptureSignals(TestCase):
    @patch("sds_gateway.api_methods.federation.reindex.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.reindex.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.reindex.get_opensearch_client")
    def test_capture_on_published_dataset_upserts(
        self,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        with _federation_on_commit():
            federation_capture_changed(sender=Capture, instance=capture)

        mock_indexer.apply_local_event.assert_called_once()
        assert (
            mock_indexer.apply_local_event.call_args.kwargs["item_type"]
            == ItemType.CAPTURE
        )
        mock_publish.assert_called_once_with(
            item_type=ItemType.CAPTURE,
            uuid=capture.uuid,
            timestamp=capture.updated_at,
        )

    @patch("sds_gateway.api_methods.federation.reindex.reindex_federated_asset")
    @patch(
        "sds_gateway.api_methods.federation.reindex.fed_doc_exists",
        return_value=False,
    )
    def test_capture_on_draft_only_skips_without_fed_doc(
        self,
        _mock_exists: MagicMock,
        mock_reindex: MagicMock,
    ) -> None:
        dataset = DatasetFactory(status=DatasetStatus.DRAFT, is_public=False)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)
        with _federation_on_commit():
            federation_capture_changed(sender=Capture, instance=capture)
        mock_reindex.assert_not_called()

    @patch("sds_gateway.api_methods.federation.reindex.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.reindex.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.reindex.get_opensearch_client")
    @patch(
        "sds_gateway.api_methods.federation.reindex.get_federated_export_doc_by_uuid",
        return_value={"is_deleted": False},
    )
    @patch(
        "sds_gateway.api_methods.federation.reindex.fed_doc_exists",
        return_value=True,
    )
    def test_deleted_capture_reindexes_with_is_deleted(
        self,
        _mock_exists: MagicMock,
        _mock_doc: MagicMock,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        _mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        capture = CaptureFactory(is_deleted=True)
        with _federation_on_commit():
            federation_capture_changed(sender=Capture, instance=capture)
        mock_indexer.apply_local_event.assert_called_once()
        assert mock_indexer.apply_local_event.call_args.kwargs["body"]["is_deleted"]


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
)
class TestDatasetDisconnectReindex(TestCase):
    @patch("sds_gateway.api_methods.federation.reindex.publish_federation_event")
    @patch("sds_gateway.api_methods.federation.reindex.LocalFederatedIndexer")
    @patch("sds_gateway.api_methods.federation.reindex.get_opensearch_client")
    @patch(
        "sds_gateway.api_methods.federation.reindex.fed_doc_exists",
        return_value=True,
    )
    def test_disconnect_captures_reindexes_orphans(
        self,
        _mock_exists: MagicMock,
        _mock_os: MagicMock,
        mock_indexer_cls: MagicMock,
        _mock_publish: MagicMock,
    ) -> None:
        mock_indexer = mock_indexer_cls.return_value
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        with _federation_on_commit():
            disconnect_captures_from_dataset(dataset)

        capture.refresh_from_db()
        assert not capture.datasets.exists()
        mock_indexer.apply_local_event.assert_called_once()
        body = mock_indexer.apply_local_event.call_args.kwargs["body"]
        assert body["public_dataset_ids"] == []

    @patch("sds_gateway.api_methods.federation.reindex.reindex_federated_asset")
    @patch(
        "sds_gateway.api_methods.federation.reindex.fed_doc_exists",
        return_value=True,
    )
    def test_dataset_soft_delete_reindexes_orphan_capture(
        self,
        _mock_exists: MagicMock,
        mock_reindex: MagicMock,
    ) -> None:
        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        capture = CaptureFactory(is_deleted=False)
        capture.datasets.add(dataset)

        with _federation_on_commit():
            dataset.soft_delete()

        capture.refresh_from_db()
        assert capture.datasets.federation_exportable().exists() is False
        capture_calls = [
            c
            for c in mock_reindex.call_args_list
            if c.args[1] == ItemType.CAPTURE and c.args[0].pk == capture.pk
        ]
        assert capture_calls


@override_settings(
    FEDERATION_ENABLED=True,
    FEDERATION_SITE_NAME="crc",
    FEDERATION_OPERATIONAL_OVERRIDE=True,
)
class TestFederationReindexOnCommit(TestCase):
    @patch("sds_gateway.api_methods.federation.reindex.reindex_federated_asset")
    def test_rollback_skips_federation_reindex(
        self,
        mock_reindex: MagicMock,
    ) -> None:
        from django.db import transaction

        dataset = DatasetFactory(status=DatasetStatus.FINAL, is_public=True)
        try:
            with transaction.atomic():
                dataset.name = "rolled back"
                dataset.save()
                raise RuntimeError("abort")
        except RuntimeError:
            pass
        mock_reindex.assert_not_called()
