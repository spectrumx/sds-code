"""Test file model deletion protection."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.db.models import QuerySet
from rest_framework.test import APITestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File

from .test_file_endpoints import create_db_file


class FileProtectionTest(APITestCase):
    """Tests for file deletion protection with different database relationships."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = get_user_model().objects.create(email="testuser@example.com")
        self.capture = Capture.objects.create(
            capture_type=CaptureType.RadioHound,
            index_name="captures-rh",
            owner=self.user,
            scan_group=uuid4(),
            top_level_dir="test-dir-rh",
        )
        self.dataset = Dataset.objects.create(
            name="test_file_model_ds",
            owner=self.user,
        )
        self._files_for_cleanup: list[File] = []

        num_files = 5
        # Files with FK relationships (deprecated)
        self.files_with_capture_fk: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture_fk:
            file_instance.capture = self.capture
            file_instance.save()

        # Files with M2M relationships (new)
        self.files_with_capture_m2m: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture_m2m:
            file_instance.captures.add(self.capture)

        # Files with both FK and M2M (during migration)
        self.files_with_capture_both: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture_both:
            file_instance.capture = self.capture
            file_instance.captures.add(self.capture)
            file_instance.save()

        self.files_with_dataset_fk: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_dataset_fk:
            file_instance.dataset = self.dataset
            file_instance.save()

        # Files with M2M dataset relationships
        self.files_with_dataset_m2m: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_dataset_m2m:
            file_instance.datasets.add(self.dataset)

        # Files with both FK and M2M dataset (during migration)
        self.files_with_dataset_both: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_dataset_both:
            file_instance.dataset = self.dataset
            file_instance.datasets.add(self.dataset)
            file_instance.save()

        self.files_with_capture_and_dataset_fk: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture_and_dataset_fk:
            file_instance.capture = self.capture
            file_instance.dataset = self.dataset
            file_instance.save()

        # Files with M2M for both capture and dataset
        self.files_with_capture_and_dataset_m2m: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture_and_dataset_m2m:
            file_instance.captures.add(self.capture)
            file_instance.datasets.add(self.dataset)

        self.files_without_associations: list[File] = [
            create_db_file(owner=self.user) for _ in range(num_files)
        ]
        self._files_for_cleanup.extend(
            [
                *self.files_with_capture_fk,
                *self.files_with_capture_m2m,
                *self.files_with_capture_both,
                *self.files_with_dataset_fk,
                *self.files_with_dataset_m2m,
                *self.files_with_dataset_both,
                *self.files_with_capture_and_dataset_fk,
                *self.files_with_capture_and_dataset_m2m,
                *self.files_without_associations,
            ]
        )

    def tearDown(self) -> None:
        """Clean up any remaining test data."""
        # attempt cleanup of remaining assets
        if self.capture:
            self.capture.delete()
        if self.dataset:
            self.dataset.delete()
        for file_instance in self._files_for_cleanup:
            if File.objects.filter(pk=file_instance.pk).exists():
                file_instance.capture = None
                file_instance.dataset = None
                file_instance.captures.clear()
                file_instance.datasets.clear()
                file_instance.save()
                file_instance.delete()
        if self.user:
            self.user.delete()

    # FK relationship tests (existing)
    def test_file_deletion_with_capture_fk(self) -> None:
        """Attempting to delete file associated with capture via FK must fail."""
        file_instance = self.files_with_capture_fk[0]
        with pytest.raises(ProtectedError):
            file_instance.delete()

    def test_file_deletion_with_dataset_fk(self) -> None:
        """Attempting to delete file associated with dataset via FK must fail."""
        file_instance = self.files_with_dataset_fk[0]
        with pytest.raises(ProtectedError):
            file_instance.delete()

    # M2M relationship tests (new)
    def test_file_deletion_with_capture_m2m(self) -> None:
        """Attempting to delete file associated with capture via M2M must fail."""
        file_instance = self.files_with_capture_m2m[0]
        with pytest.raises(ProtectedError):
            file_instance.delete()

    def test_file_deletion_with_dataset_m2m(self) -> None:
        """Attempting to delete file associated with dataset via M2M must fail."""
        file_instance = self.files_with_dataset_m2m[0]
        with pytest.raises(ProtectedError):
            file_instance.delete()

    # Both FK and M2M tests (during migration)
    def test_file_deletion_with_capture_both(self) -> None:
        """Attempting to delete file with both FK and M2M capture must fail."""
        file_instance = self.files_with_capture_both[0]
        with pytest.raises(ProtectedError):
            file_instance.delete()

    def test_file_deletion_with_dataset_both(self) -> None:
        """Attempting to delete file with both FK and M2M dataset must fail."""
        file_instance = self.files_with_dataset_both[0]
        with pytest.raises(ProtectedError):
            file_instance.delete()

    def test_file_deletion_without_associations(self) -> None:
        """A file without any associations can be deleted successfully."""
        file_instance = self.files_without_associations[0]
        file_instance.delete()
        assert not File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_capture_fk(self) -> None:
        """Attempting to bulk delete files associated with captures via FK must fail."""
        files = self.files_with_capture_fk
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        with pytest.raises(ProtectedError):
            q_set.delete()
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_capture_m2m(self) -> None:
        """Bulk delete files associated with captures via M2M must fail."""
        files = self.files_with_capture_m2m
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        with pytest.raises(ProtectedError):
            q_set.delete()
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_dataset_fk(self) -> None:
        """Attempting to bulk delete files associated with datasets via FK must fail."""
        files = self.files_with_dataset_fk
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        with pytest.raises(ProtectedError):
            q_set.delete()
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_dataset_m2m(self) -> None:
        """Bulk delete files associated with datasets via M2M must fail."""
        files = self.files_with_dataset_m2m
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        with pytest.raises(ProtectedError):
            q_set.delete()
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_capture_and_dataset_fk(self) -> None:
        """Bulk delete files with captures and datasets via FK must fail."""
        files = self.files_with_capture_and_dataset_fk
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        with pytest.raises(ProtectedError):
            q_set.delete()
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_capture_and_dataset_m2m(self) -> None:
        """Bulk delete files with captures and datasets via M2M must fail."""
        files = self.files_with_capture_and_dataset_m2m
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        with pytest.raises(ProtectedError):
            q_set.delete()
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_without_associations(self) -> None:
        """Bulk deleting files without any associations in bulk should succeed."""
        files = self.files_without_associations
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        q_set.delete()
        for file_instance in files:
            assert not File.objects.filter(pk=file_instance.pk).exists()

    def test_soft_deletion_is_protected_fk(self) -> None:
        """Soft deletion of files associated via FK must fail."""
        protected_files = [
            self.files_with_capture_fk[0],
            self.files_with_dataset_fk[0],
            self.files_with_capture_and_dataset_fk[0],
        ]
        for file_instance in protected_files:
            with pytest.raises(ProtectedError):
                file_instance.soft_delete()
        for file_instance in protected_files:
            q_set = File.objects.filter(pk=file_instance.pk)
            assert q_set.exists()
            target_file = q_set.first()
            assert target_file is not None
            assert not target_file.is_deleted

    def test_soft_deletion_is_protected_m2m(self) -> None:
        """Soft deletion of files associated via M2M must fail."""
        protected_files = [
            self.files_with_capture_m2m[0],
            self.files_with_dataset_m2m[0],
            self.files_with_capture_and_dataset_m2m[0],
        ]
        for file_instance in protected_files:
            with pytest.raises(ProtectedError):
                file_instance.soft_delete()
        for file_instance in protected_files:
            q_set = File.objects.filter(pk=file_instance.pk)
            assert q_set.exists()
            target_file = q_set.first()
            assert target_file is not None
            assert not target_file.is_deleted

    def test_soft_deletion_is_allowed(self) -> None:
        """Soft deletion of files without any associations should succeed."""
        file_instance = self.files_without_associations[0]
        file_instance.soft_delete()
        sd_file = File.objects.filter(pk=file_instance.pk).first()
        assert sd_file is not None
        assert sd_file.is_deleted
