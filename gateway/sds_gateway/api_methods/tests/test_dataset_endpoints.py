"""Tests for dataset endpoints."""

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

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

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()
        self.user = UserFactory()
        self.client.force_authenticate(user=self.user)
        self.dataset = DatasetFactory(owner=self.user)
        
        # Mock OpenSearch to prevent errors in all tests
        self.opensearch_patcher = patch('sds_gateway.api_methods.helpers.index_handling.retrieve_indexed_metadata')
        self.mock_retrieve = self.opensearch_patcher.start()
        # Return empty dict for any capture input
        self.mock_retrieve.return_value = {}

    def tearDown(self):
        """Clean up after tests."""
        self.opensearch_patcher.stop()

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
        assert data["count"] == 2
        
        # Check results structure
        results = data["results"]
        assert len(results) == 2
        
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

        # Create files associated with the capture using MinIO mocking
        with MockMinIOContext(b"test_content"):
            capture_file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=capture
            )
            capture_file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=capture
            )

            # Create files directly associated with the dataset
            dataset_file = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )

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
        assert data["count"] == 3
        
        # Check results structure
        results = data["results"]
        assert len(results) == 3
        
        # Verify capture file info structure
        capture_files = [f for f in results if f["capture"] is not None]
        assert len(capture_files) == 2
        
        for file_info in capture_files:
            assert file_info["capture"]["uuid"] == str(capture.uuid)
            assert file_info["capture"]["name"] == capture.name

    def test_get_dataset_files_with_shared_captures(self):
        """Test dataset files manifest including files from shared captures."""
        # Create another user who will own the capture
        other_user = UserFactory()
        
        # Create a capture owned by another user and associated with the dataset
        capture = Capture.objects.create(
            owner=other_user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            index_name="test_index",  # Add required index_name
            name="test_capture",  # Add name for better identification
        )

        # Create a share permission for the dataset with the current user
        dataset_share_permission = UserSharePermission.objects.create(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            is_enabled=True,
        )

        # Create files associated with the shared capture using MinIO mocking
        with MockMinIOContext(b"test_content"):
            capture_file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=capture
            )
            capture_file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=capture
            )

            # Create files directly associated with the dataset
            dataset_file = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )

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
        assert data["count"] == 3
        
        # Check results structure
        results = data["results"]
        assert len(results) == 3
        
        # Verify shared capture file info structure
        capture_files = [f for f in results if f["capture"] is not None]
        assert len(capture_files) == 2
        
        for file_info in capture_files:
            assert file_info["capture"]["uuid"] == str(capture.uuid)
            assert file_info["capture"]["name"] == capture.name

    def test_get_dataset_files_with_both_owned_and_shared_captures(self):
        """Test dataset files manifest including files from both owned and shared captures."""
        # Create another user who will own a shared capture
        other_user = UserFactory()
        
        # Create an owned capture
        owned_capture = Capture.objects.create(
            owner=self.user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="owned_channel",
            index_name="owned_index",  # Add required index_name
            name="owned_capture",  # Add name for better identification
        )

        # Create a shared capture owned by another user
        shared_capture = Capture.objects.create(
            owner=other_user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="shared_channel",
            index_name="shared_index",  # Add required index_name
            name="shared_capture",  # Add name for better identification
        )

        # Create a share permission for the dataset with the current user
        dataset_share_permission = UserSharePermission.objects.create(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.DATASET,
            item_uuid=self.dataset.uuid,
            is_enabled=True,
        )

        # Create files associated with both captures using MinIO mocking
        with MockMinIOContext(b"test_content"):
            # Files from owned capture
            owned_capture_file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=owned_capture
            )
            owned_capture_file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, capture=owned_capture
            )

            # Files from shared capture
            shared_capture_file1 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=shared_capture
            )
            shared_capture_file2 = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=shared_capture
            )

            # Files directly associated with the dataset
            dataset_file = create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Check pagination structure
        assert "count" in data
        assert "next" in data
        assert "previous" in data
        assert "results" in data
        
        # Check total file count (5 files: 2 from owned capture + 2 from shared capture + 1 from dataset)
        assert data["count"] == 5
        
        # Check results structure
        results = data["results"]
        assert len(results) == 5
        
        # Verify owned capture file info structure
        owned_capture_files = [f for f in results if f["capture"] is not None and f["capture"]["uuid"] == str(owned_capture.uuid)]
        assert len(owned_capture_files) == 2
        
        for file_info in owned_capture_files:
            assert file_info["capture"]["uuid"] == str(owned_capture.uuid)
            assert file_info["capture"]["name"] == owned_capture.name

        # Verify shared capture file info structure
        shared_capture_files = [f for f in results if f["capture"] is not None and f["capture"]["uuid"] == str(shared_capture.uuid)]
        assert len(shared_capture_files) == 2
        
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
        """Test that the pagination response has the correct structure for SDK consumption."""
        # Create test files
        with MockMinIOContext(b"test_content"):
            create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )

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
        with MockMinIOContext(b"test_content"):
            for i in range(35):  # More than default page size of 30
                create_file_with_minio_mock(
                    file_content=b"test_content", 
                    owner=self.user, 
                    dataset=self.dataset,
                    name=f"file_{i}.h5"
                )

        url = reverse("api:datasets-files", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        
        # Check pagination structure
        assert data["count"] == 35
        assert len(data["results"]) == 30  # Default page size
        assert data["next"] is not None  # Should have next page
        assert data["previous"] is None  # First page

        # Test second page
        response = self.client.get(f"{url}?page=2")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert len(data["results"]) == 5  # Remaining files
        assert data["next"] is None  # No more pages
        assert data["previous"] is not None  # Has previous page

        # Test custom page size
        response = self.client.get(f"{url}?page_size=10")
        assert response.status_code == status.HTTP_200_OK
        
        data = response.json()
        assert len(data["results"]) == 10
        assert data["next"] is not None  # Should have next page

    def test_get_dataset_files_shared_capture_disabled_permission(self):
        """Test that disabled share permissions don't grant access to capture files."""
        # Create another user who will own the dataset and capture
        other_user = UserFactory()
        
        # Create a dataset owned by another user
        other_dataset = DatasetFactory(owner=other_user)
        
        # Create a capture owned by another user and associated with the other dataset
        capture = Capture.objects.create(
            owner=other_user,
            dataset=other_dataset,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
            index_name="test_index",  # Add required index_name
            name="test_capture",  # Add name for better identification
        )

        # Create a disabled share permission for the dataset
        dataset_share_permission = UserSharePermission.objects.create(
            owner=other_user,
            shared_with=self.user,
            item_type=ItemType.DATASET,
            item_uuid=other_dataset.uuid,
            is_enabled=False,  # Disabled permission
        )

        # Create files associated with the capture
        with MockMinIOContext(b"test_content"):
            create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, capture=capture
            )

            # Create files directly associated with the dataset
            dataset_file = create_file_with_minio_mock(
                file_content=b"test_content", owner=other_user, dataset=other_dataset
            )

        url = reverse("api:datasets-files", kwargs={"pk": other_dataset.uuid})
        response = self.client.get(url)

        # Should get 403 Forbidden because the share permission is disabled
        assert response.status_code == status.HTTP_403_FORBIDDEN

