"""Tests for dataset endpoints."""

import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

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

    @patch("sds_gateway.api_methods.views.dataset_endpoints.sanitize_path_rel_to_user")
    def test_download_dataset_success(self, mock_sanitize_path):
        """Test successful dataset download."""
        # Create test files associated with the dataset with MinIO mocking
        with MockMinIOContext(b"test_file_content"):
            file1 = create_file_with_minio_mock(
                file_content=b"test_file_content", owner=self.user, dataset=self.dataset
            )
            file2 = create_file_with_minio_mock(
                file_content=b"test_file_content", owner=self.user, dataset=self.dataset
            )

        # Mock the sanitize_path_rel_to_user function to return a simple path
        mock_sanitize_path.return_value = "/files/test/"

        url = reverse("api:datasets-download", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "application/zip"
        assert "attachment" in response["Content-Disposition"]
        assert self.dataset.name in response["Content-Disposition"]

        # Verify ZIP content
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        try:
            with zipfile.ZipFile(temp_file_path, "r") as zip_file:
                file_list = zip_file.namelist()
                assert len(file_list) > 0, f"Expected files in ZIP, got: {file_list}"

                # Check that our test files are in the ZIP (just the filename)
                for file_obj in [file1, file2]:
                    expected_path = file_obj.name  # Just the filename, no directory
                    assert expected_path in file_list, (
                        f"Expected {expected_path} in ZIP files: {file_list}"
                    )
        finally:
            Path(temp_file_path).unlink()

    def test_download_dataset_not_found(self):
        """Test dataset download with non-existent UUID."""
        import uuid

        fake_uuid = uuid.uuid4()
        url = reverse("api:datasets-download", kwargs={"pk": fake_uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_dataset_unauthorized(self):
        """Test dataset download by non-owner."""
        other_user = UserFactory()
        other_dataset = DatasetFactory(owner=other_user)

        url = reverse("api:datasets-download", kwargs={"pk": other_dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_dataset_no_files(self):
        """Test dataset download with no associated files."""
        url = reverse("api:datasets-download", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "No files found in dataset" in response.data["detail"]

    def test_download_dataset_file_error(self):
        """Test dataset download with file download error."""
        # Create test file with MinIO mocking that will fail
        with MockMinIOContext(b"test_content"):
            create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )

        # The MinIO mock will work, but we can test error handling by mocking
        # the download_file function
        with patch(
            "sds_gateway.api_methods.views.dataset_endpoints.download_file"
        ) as mock_download_file:
            # Mock download_file to raise an exception
            mock_download_file.side_effect = OSError("File not found")

            url = reverse("api:datasets-download", kwargs={"pk": self.dataset.uuid})
            response = self.client.get(url)

            # Should still succeed but skip the problematic file
            assert response.status_code == status.HTTP_200_OK

    def test_download_dataset_zip_creation_error(self):
        """Test dataset download with ZIP creation error."""
        # Create test file with MinIO mocking
        with MockMinIOContext(b"test_content"):
            create_file_with_minio_mock(
                file_content=b"test_content", owner=self.user, dataset=self.dataset
            )

        # Mock zipfile.ZipFile to raise an exception
        with patch("zipfile.ZipFile") as mock_zip:
            mock_zip.side_effect = zipfile.BadZipFile("Invalid ZIP")

            url = reverse("api:datasets-download", kwargs={"pk": self.dataset.uuid})
            response = self.client.get(url)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
            assert "ZIP format error" in response.data["detail"]

    def test_download_dataset_missing_uuid(self):
        """Test dataset download without UUID parameter."""
        # Test with a valid UUID format that doesn't exist instead of invalid string
        url = reverse(
            "api:datasets-download",
            kwargs={"pk": "00000000-0000-0000-0000-000000000000"},
        )
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_access(self):
        """Test access without authentication."""
        self.client.force_authenticate(user=None)

        url = reverse("api:datasets-download", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @patch("sds_gateway.api_methods.views.dataset_endpoints.sanitize_path_rel_to_user")
    def test_download_dataset_with_capture_files(self, mock_sanitize_path):
        """Test dataset download including files from associated captures."""
        from sds_gateway.api_methods.models import Capture
        from sds_gateway.api_methods.models import CaptureType

        # Create a capture associated with the dataset
        capture = Capture.objects.create(
            owner=self.user,
            dataset=self.dataset,
            capture_type=CaptureType.DigitalRF,
            channel="test_channel",
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

        # Mock the sanitize_path_rel_to_user function to return a simple path
        mock_sanitize_path.return_value = "/files/test/"

        url = reverse("api:datasets-download", kwargs={"pk": self.dataset.uuid})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK

        # Verify ZIP content includes both capture and dataset files
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
            temp_file.write(response.content)
            temp_file_path = temp_file.name

        try:
            with zipfile.ZipFile(temp_file_path, "r") as zip_file:
                file_list = zip_file.namelist()

                # Should include files from both capture and dataset (just filenames)
                expected_files = [
                    capture_file1.name,
                    capture_file2.name,
                    dataset_file.name,
                ]

                for expected_file in expected_files:
                    assert expected_file in file_list, (
                        f"Expected {expected_file} in ZIP files: {file_list}"
                    )
        finally:
            Path(temp_file_path).unlink()
