"""Test file model deletion protection."""

from uuid import uuid4

import pytest
from django.contrib.auth import get_user_model
from django.db.models import ProtectedError
from django.db.models import QuerySet
from pydantic import BaseModel
from rest_framework.test import APITestCase

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File

from .test_file_endpoints import create_db_file


class TestUser(BaseModel):
    email: str


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
        self._files_for_cleanup = []

        num_files = 5
        self.files_with_capture: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture:
            file_instance.capture = self.capture
            file_instance.save()
        self.files_with_dataset: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_dataset:
            file_instance.dataset = self.dataset
            file_instance.save()
        self.files_with_capture_and_dataset: list[File] = [
            create_db_file(
                owner=self.user,
            )
            for _ in range(num_files)
        ]
        for file_instance in self.files_with_capture_and_dataset:
            file_instance.capture = self.capture
            file_instance.dataset = self.dataset
            file_instance.save()
        self.files_without_associations: list[File] = [
            create_db_file(owner=self.user) for _ in range(num_files)
        ]
        self._files_for_cleanup.extend(self.files_with_capture)
        self._files_for_cleanup.extend(self.files_with_dataset)
        self._files_for_cleanup.extend(self.files_with_capture_and_dataset)
        self._files_for_cleanup.extend(self.files_without_associations)

        assert len(self._files_for_cleanup) == 4 * num_files, (
            "Test setup failed to create the expected number of files."
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
                file_instance.save()
                file_instance.delete()
        if self.user:
            self.user.delete()

    def test_file_deletion_with_capture(self) -> None:
        """Attempting to delete file associated with capture must fail."""
        # ARRANGE: create capture and associate file with capture
        file_instance = self.files_with_capture[0]

        # ACT and ASSERT: ensure deletion raises ProtectedError
        with pytest.raises(ProtectedError):
            file_instance.delete()

    def test_file_deletion_with_dataset(self) -> None:
        """Attempting to delete file associated with dataset must fail."""
        # ARRANGE: create dataset and associate file with dataset
        file_instance = self.files_with_dataset[0]

        # ACT and ASSERT: ensure deletion raises ProtectedError
        with pytest.raises(ProtectedError):
            file_instance.delete()

    def test_file_deletion_without_associations(self) -> None:
        """A file without any associations can be deleted successfully."""
        # ARRANGE: create file without associations
        file_instance = self.files_without_associations[0]

        # ACT: delete the file
        file_instance.delete()

        # ASSERT: ensure the file no longer exists
        assert not File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_capture(self) -> None:
        """Attempting to bulk delete files associated with captures must fail."""
        # ARRANGE: create capture and associate multiple files with capture
        files = self.files_with_capture

        # ACT and ASSERT: ensure bulk deletion raises ProtectedError
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)

        with pytest.raises(ProtectedError):
            q_set.delete()

        # ASSERT all files were preserved
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_dataset(self) -> None:
        """Attempting to bulk delete files associated with datasets must fail."""
        # ARRANGE: create dataset and associate multiple files with dataset
        files = self.files_with_dataset

        # ACT and ASSERT: ensure bulk deletion raises ProtectedError
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)

        with pytest.raises(ProtectedError):
            q_set.delete()

        # ASSERT all files were preserved
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_with_capture_and_dataset(self) -> None:
        """Bulk deleting files associated with captures and datasets must fail."""
        # ARRANGE: create capture and dataset, and associate multiple files with both
        files = self.files_with_capture_and_dataset

        # ACT and ASSERT: ensure bulk deletion raises ProtectedError
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)

        with pytest.raises(ProtectedError):
            q_set.delete()

        # ASSERT all files were preserved
        for file_instance in files:
            assert File.objects.filter(pk=file_instance.pk).exists()

    def test_bulk_file_deletion_without_associations(self) -> None:
        """Bulk deleting files without any associations in bulk should succeed."""
        # ARRANGE: create multiple files without associations
        files = self.files_without_associations

        # ACT: bulk delete the files
        file_ids = [file_instance.pk for file_instance in files]
        q_set: QuerySet[File] = File.objects.filter(pk__in=file_ids)
        q_set.delete()

        # ASSERT: ensure none of the files exist
        for file_instance in files:
            assert not File.objects.filter(pk=file_instance.pk).exists()
