"""Tests for dataset endpoints."""

from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.tests.factories import DatasetFactory
from sds_gateway.api_methods.tests.factories import MockMinIOContext
from sds_gateway.api_methods.tests.factories import UserFactory
from sds_gateway.api_methods.tests.factories import create_file_with_minio_mock


class DatasetEndpointsTestCase(TestCase):
    """Test cases for dataset endpoints."""

    # Constants for test assertions
    EXPECTED_DATASET_FILES = 2
    EXPECTED_CAPTURE_FILES = 2
    EXPECTED_TOTAL_FILES_3 = 3
    EXPECTED_TOTAL_FILES_5 = 5
    EXPECTED_PAGINATION_COUNT = 35
    EXPECTED_PAGE_SIZE = 30
    EXPECTED_REMAINING_FILES = 5
    EXPECTED_CUSTOM_PAGE_SIZE = 10

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.dataset = DatasetFactory(owner=self.user)

        # Track created objects for cleanup
        self.created_files = []
        self.created_captures = []
        self.created_datasets = [self.dataset]
        self.created_share_permissions = []
        self.created_users = [self.user]

        # Mock OpenSearch to prevent errors in all tests
        self.opensearch_patcher = patch(
            "sds_gateway.api_methods.helpers.index_handling.retrieve_indexed_metadata"
        )
        self.mock_retrieve = self.opensearch_patcher.start()
        # Return empty dict for any capture input
        self.mock_retrieve.return_value = {}

    def tearDown(self):
        """Clean up after tests."""
        self.opensearch_patcher.stop()

        # Clean up created objects in reverse dependency order
        # First, disassociate files from datasets and captures
        # to avoid protection errors
        self._disassociate_files()

        # Then delete dataset connections
        self._cleanup_dataset_connections()

        # Then datasets (they can be deleted once files and captures are gone)
        for dataset in self.created_datasets:
            if dataset.pk:
                dataset.delete()

        # Finally users (they can be deleted once all dependent objects are gone)
        for user in self.created_users:
            if user.pk:
                user.delete()

    def _disassociate_files(self):
        """Disassociate files from datasets and captures."""
        for file_obj in self.created_files:
            if file_obj.pk:  # Only process if it exists in database
                # Disassociate from dataset and capture to allow deletion
                file_obj.dataset = None
                file_obj.capture = None
                file_obj.save()

    def _cleanup_dataset_connections(self):
        """Delete dataset connections."""
        # Delete files (after disassociation)
        for file_obj in self.created_files:
            if file_obj.pk:
                file_obj.delete()

        # Delete captures (they reference datasets)
        for capture in self.created_captures:
            if capture.pk:
                capture.delete()

        # Delete permissions (they reference datasets)
        for permission in self.created_share_permissions:
            if permission.pk:
                permission.delete()

    def test_get_dataset_files_success(self):
        """Test successful dataset files manifest retrieval."""
        # Create test files associated with the dataset with MinIO mocking
        with MockMinIOContext(b"test_file_content"):
            file1 = create_file_with_minio_mock(
                file_content=b"test_file_content", owner=self.user, dataset=self.dataset
            )
            file2 = create_file_with_minio_mock(
                file_content=b"test_file_content", owner=self.user, dataset=self.dataset
            )
            # Track created files for cleanup
            self.created_files.extend([file1, file2])

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check pagination structure
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

        # Check file count
        assert data["count"] == self.EXPECTED_DATASET_FILES

        # Check results structure
        results = data["results"]
        assert len(results) == self.EXPECTED_DATASET_FILES

        # Verify file info structure
        for file_info in results:
            assert "uuid" in file_info
            assert "name" in file_info
            assert "directory" in file_info
            assert "size" in file_info
            assert "media_type" in file_info
            assert file_info["capture"] is None

    def test_get_dataset_files_with_owned_captures(self):
        """Test dataset files manifest including files from owned captures."""
        # Create a capture owned by the user and associated with the dataset
        capture = Capture.objects.create(
            owner=self.user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            index_name="test_index",  # Add required index_name
            name="test_capture",  # Add name for better identification
        )
        # Track created capture for cleanup
        self.created_captures.append(capture)

        # Create files associated with the capture using MinIO mocking
        with MockMinIOContext(b"test_content"):
            file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=capture
            )
            file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=capture
            )

            # Create files directly associated with the dataset
            file3 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )
            # Track created files for cleanup
            self.created_files.extend([file1, file2, file3])

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check pagination structure
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

        # Check total file count (3 files: 2 from capture + 1 from dataset)
        assert data["count"] == self.EXPECTED_TOTAL_FILES_3

        # Check results structure
        results = data["results"]
        assert len(results) == self.EXPECTED_TOTAL_FILES_3

        # Verify capture file info structure
        capture_files = [f for f in results if f["capture"] is not None]
        assert len(capture_files) == self.EXPECTED_CAPTURE_FILES

        for file_info in capture_files:
            assert file_info["capture"]["uuid"] == str(capture.uuid)
            assert file_info["capture"]["name"] == capture.name

    def test_get_dataset_files_with_shared_captures(self):
        """Test dataset files manifest including files from shared captures."""
        # Create another user who will own the capture
        other_user = UserFactory()
        # Track created user for cleanup
        self.created_users.append(other_user)

        # Create a capture owned by another user and associated with the dataset
        capture = Capture.objects.create(
            owner=other_user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            index_name="test_index",  # Add required index_name
            name="test_capture",  # Add name for better identification
        )
        # Track created capture for cleanup
        self.created_captures.append(capture)

        # Create a share permission for the dataset with the current user
        permission = UserSharePermission.objects.create(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            is_enabled=True,
        )
        # Track created permission for cleanup
        self.created_share_permissions.append(permission)

        # Create files associated with the shared capture using MinIO mocking
        with MockMinIOContext(b"test_content"):
            file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=capture
            )
            file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=capture
            )

            # Create files directly associated with the dataset
            file3 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )
            # Track created files for cleanup
            self.created_files.extend([file1, file2, file3])

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check pagination structure
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

        # Check total file count (3 files: 2 from shared capture + 1 from dataset)
        assert data["count"] == self.EXPECTED_TOTAL_FILES_3

        # Check results structure
        results = data["results"]
        assert len(results) == self.EXPECTED_TOTAL_FILES_3

        # Verify shared capture file info structure
        capture_files = [f for f in results if f["capture"] is not None]
        assert len(capture_files) == self.EXPECTED_CAPTURE_FILES

        for file_info in capture_files:
            assert file_info["capture"]["uuid"] == str(capture.uuid)
            assert file_info["capture"]["name"] == capture.name

    def test_get_dataset_files_with_both_owned_and_shared_captures(self):
        """Test dataset files manifest with both owned and shared captures."""
        # Create another user who will own a shared capture
        other_user = UserFactory()
        # Track created user for cleanup
        self.created_users.append(other_user)

        # Create an owned capture
        owned_capture = Capture.objects.create(
            owner=self.user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="owned_channel",
            index_name="owned_index",  # Add required index_name
            name="owned_capture",  # Add name for better identification
        )
        # Track created capture for cleanup
        self.created_captures.append(owned_capture)

        # Create a shared capture owned by another user
        shared_capture = Capture.objects.create(
            owner=other_user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="shared_channel",
            index_name="shared_index",  # Add required index_name
            name="shared_capture",  # Add name for better identification
        )
        # Track created capture for cleanup
        self.created_captures.append(shared_capture)

        # Create a share permission for the dataset with the current user
        permission = UserSharePermission.objects.create(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            is_enabled=True,
        )
        # Track created permission for cleanup
        self.created_share_permissions.append(permission)

        # Create files associated with both captures using MinIO mocking
        with MockMinIOContext(b"test_content"):
            # Files from owned capture
            file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=owned_capture
            )
            file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=owned_capture
            )

            # Files from shared capture
            file3 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=shared_capture
            )
            file4 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=shared_capture
            )

            # Files directly associated with the dataset
            file5 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )
            # Track created files for cleanup
            self.created_files.extend([file1, file2, file3, file4, file5])

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check pagination structure
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data

        # Check total file count (5 files: 2 owned + 2 shared + 1 dataset)
        assert data["count"] == self.EXPECTED_TOTAL_FILES_5

        # Check results structure
        results = data["results"]
        assert len(results) == self.EXPECTED_TOTAL_FILES_5

        # Verify owned capture file info structure
        owned_capture_files = [
            f
            for f in results
            if f["capture"] is not None
            and f["capture"]["uuid"] == str(owned_capture.uuid)
        ]
        assert len(owned_capture_files) == self.EXPECTED_CAPTURE_FILES

        for file_info in owned_capture_files:
            assert file_info["capture"]["uuid"] == str(owned_capture.uuid)
            assert file_info["capture"]["name"] == owned_capture.name

        # Verify shared capture file info structure
        shared_capture_files = [
            f
            for f in results
            if f["capture"] is not None
            and f["capture"]["uuid"] == str(shared_capture.uuid)
        ]
        assert len(shared_capture_files) == self.EXPECTED_CAPTURE_FILES

        for file_info in shared_capture_files:
            assert file_info["capture"]["uuid"] == str(shared_capture.uuid)
            assert file_info["capture"]["name"] == shared_capture.name

    def test_get_dataset_files_not_found(self):
        """Test dataset files manifest with non-existent UUID."""
        import uuid

        fake_uuid = uuid.uuid4()
        url = reverse("api:datasets-files", kwargs={"pk": fake_uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_dataset_files_unauthorized(self):
        """Test dataset files manifest by non-owner."""
        other_user = UserFactory()
        other_dataset = DatasetFactory(owner=other_user)
        # Track created objects for cleanup
        self.created_users.append(other_user)
        self.created_datasets.append(other_dataset)

        url = reverse("api:datasets-files", kwargs={"pk": other_dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_dataset_files_no_files(self):
        """Test dataset files manifest with no associated files."""
        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "No files found in dataset" in response.data["detail"]

    def test_get_dataset_files_missing_uuid(self):
        """Test dataset files manifest without UUID parameter."""
        # Use a valid UUID format that doesn't exist to test the 404 case
        import uuid

        fake_uuid = uuid.uuid4()
        url = reverse("api:datasets-files", kwargs={"pk": fake_uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_dataset_files_unauthenticated_access(self):
        """Test access without authentication."""
        self.client.force_authenticate(user=None)

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_dataset_files_pagination_structure(self):
        """Test pagination response structure for SDK consumption."""
        # Create test files
        with MockMinIOContext(b"test_content"):
            file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )
            # Track created file for cleanup
            self.created_files.append(file1)

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Verify pagination structure
        required_pagination_keys = ["count", "next", "previous", "results"]
        for key in required_pagination_keys:
            assert key in data, f"Missing pagination key: {key}"

        # Verify results structure
        assert isinstance(data["results"], list)
        assert data["count"] == 1

        # Verify file info structure (if files exist)
        if data["results"]:
            file_info = data["results"][0]
            required_file_keys = ["uuid", "name", "directory", "size", "media_type"]
            for key in required_file_keys:
                assert key in file_info, f"Missing file info key: {key}"

    def test_get_dataset_files_pagination_parameters(self):
        """Test pagination parameters work correctly."""
        # Create multiple test files
        created_files = []
        with MockMinIOContext(b"test_content"):
            for i in range(
                self.EXPECTED_PAGINATION_COUNT
            ):  # More than default page size of 30
                file_obj = create_file_with_minio_mock(
                    file_content=b"test_content",
                    owner=self.user,
                    dataset=self.dataset,
                    name=f"file_{i}.h5",
                )
                created_files.append(file_obj)
        # Track created files for cleanup
        self.created_files.extend(created_files)

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()

        # Check pagination structure
        assert data["count"] == self.EXPECTED_PAGINATION_COUNT
        assert len(data["results"]) == self.EXPECTED_PAGE_SIZE  # Default page size
        assert data["next"] is not None  # Should have next page
        assert data["previous"] is None  # First page

        # Test second page
        response = self.client.get(f"{url}?page=2")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data["results"]) == self.EXPECTED_REMAINING_FILES  # Remaining files
        assert data["next"] is None  # No more pages
        assert data["previous"] is not None  # Has previous page

        # Test custom page size
        response = self.client.get(f"{url}?page_size={self.EXPECTED_CUSTOM_PAGE_SIZE}")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert len(data["results"]) == self.EXPECTED_CUSTOM_PAGE_SIZE
        assert data["next"] is not None  # Should have next page

    def test_get_dataset_files_shared_capture_disabled_permission(self):
        """Test that disabled share permissions don't grant access to capture files."""
        # Create another user who will own the dataset and capture
        other_user = UserFactory()
        # Track created user for cleanup
        self.created_users.append(other_user)

        # Create a dataset owned by another user
        other_dataset = DatasetFactory(owner=other_user)
        # Track created dataset for cleanup
        self.created_datasets.append(other_dataset)

        # Create a capture owned by another user and associated with the other dataset
        capture = Capture.objects.create(
            owner=other_user,
            dataset=other_dataset,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            index_name="test_index",  # Add required index_name
            name="test_capture",  # Add name for better identification
        )
        # Track created capture for cleanup
        self.created_captures.append(capture)

        # Create a disabled share permission for the dataset
        permission = UserSharePermission.objects.create(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.DATASET,
            item_uuid=other_dataset.uuid,
            is_enabled=False,  # Disabled permission
        )
        # Track created permission for cleanup
        self.created_share_permissions.append(permission)

        # Create files associated with the capture
        with MockMinIOContext(b"test_content"):
            file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=capture
            )

            # Create files directly associated with the dataset
            file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, dataset=other_dataset
            )
            # Track created files for cleanup
            self.created_files.extend([file1, file2])

        url = reverse("api:datasets-files", kwargs={"pk": other_dataset.uuid})
        response = self.client.get(url)

        # Should get 403 Forbidden because the share permission is disabled
        assert response.status_code == status.HTTP_403_FORBIDDEN
