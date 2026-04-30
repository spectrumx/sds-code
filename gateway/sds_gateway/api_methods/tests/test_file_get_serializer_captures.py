"""Tests for FileGetSerializer ``capture`` / ``captures`` merge (SDK-facing shape)."""

from unittest.mock import patch

from django.test import TestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.tests.factories import DatasetFactory
from sds_gateway.api_methods.tests.factories import UserFactory
from sds_gateway.api_methods.tests.test_file_endpoints import create_db_file


class FileGetSerializerCapturesTestCase(TestCase):
    """``to_representation`` merges M2M ``captures`` with legacy ``capture`` FK."""

    def setUp(self) -> None:
        self.user = UserFactory()
        self.dataset = DatasetFactory(owner=self.user)
        self.capture_a = Capture.objects.create(
            owner=self.user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="ch-a",
            index_name="ix-a",
            name="cap-a",
        )
        self.capture_b = Capture.objects.create(
            owner=self.user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="ch-b",
            index_name="ix-b",
            name="cap-b",
        )
        self.opensearch_patcher = patch(
            "sds_gateway.api_methods.helpers.index_handling.retrieve_indexed_metadata",
            return_value={},
        )
        self.opensearch_patcher.start()

    def tearDown(self) -> None:
        self.opensearch_patcher.stop()
        File.objects.filter(owner=self.user).delete()
        Capture.objects.filter(owner=self.user).delete()
        self.dataset.delete()
        self.user.delete()

    def _serialize(self, file_obj: File) -> dict:
        return FileGetSerializer(file_obj).data

    def test_legacy_fk_only_populates_both_capture_and_captures(self) -> None:
        f = create_db_file(owner=self.user)
        f.capture = self.capture_a
        f.save(update_fields=["capture"])
        data = self._serialize(f)
        assert data["capture"] is not None
        assert data["capture"]["uuid"] == str(self.capture_a.uuid)
        assert len(data["captures"]) == 1
        assert data["captures"][0]["uuid"] == str(self.capture_a.uuid)

    def test_m2m_only_populates_both(self) -> None:
        f = create_db_file(owner=self.user)
        f.captures.add(self.capture_a)
        data = self._serialize(f)
        assert data["capture"] is not None
        assert data["capture"]["uuid"] == str(self.capture_a.uuid)
        assert len(data["captures"]) == 1
        assert data["captures"][0]["uuid"] == str(self.capture_a.uuid)

    def test_fk_and_m2m_same_capture_deduplicated(self) -> None:
        f = create_db_file(owner=self.user)
        f.capture = self.capture_a
        f.save(update_fields=["capture"])
        f.captures.add(self.capture_a)
        data = self._serialize(f)
        assert len(data["captures"]) == 1
        assert data["captures"][0]["uuid"] == str(self.capture_a.uuid)
        assert data["capture"]["uuid"] == str(self.capture_a.uuid)

    def test_m2m_two_captures_fk_none_first_in_uuid_order(self) -> None:
        f = create_db_file(owner=self.user)
        f.captures.add(self.capture_b, self.capture_a)
        data = self._serialize(f)
        ordered = sorted([str(self.capture_a.uuid), str(self.capture_b.uuid)])
        assert [c["uuid"] for c in data["captures"]] == ordered
        assert data["capture"]["uuid"] == ordered[0]

    def test_no_capture_links_both_null_or_empty(self) -> None:
        f = create_db_file(owner=self.user)
        data = self._serialize(f)
        assert data["capture"] is None
        assert data["captures"] == []
