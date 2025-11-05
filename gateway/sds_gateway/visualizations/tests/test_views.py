"""Tests for visualization views."""

import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.visualizations.models import PostProcessedData
from sds_gateway.visualizations.models import ProcessingStatus
from sds_gateway.visualizations.models import ProcessingType

User = get_user_model()


class WaterfallVisualizationViewTestCases(TestCase):
    """Test cases for WaterfallVisualizationView."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        # Create test capture
        self.capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            index_name="test-index",
            owner=self.user,
            top_level_dir="/test/dir",
        )

        # Set up URL
        self.waterfall_url = reverse(
            "visualizations:waterfall",
            kwargs={"capture_uuid": self.capture.uuid},
        )

    def test_waterfall_view_requires_login(self) -> None:
        """Test that the waterfall view requires login."""
        response = self.client.get(self.waterfall_url)
        assert response.status_code == status.HTTP_302_FOUND  # Redirect to login

        # Follow redirect to confirm it's going to login
        login_url = response.url
        assert "login" in login_url

    def test_waterfall_view_with_authenticated_user_200(self) -> None:
        """Test that authenticated users can access the waterfall view."""
        self.client.force_login(self.user)

        response = self.client.get(self.waterfall_url)
        assert response.status_code == status.HTTP_200_OK

        # Check template is used
        assert "visualizations/waterfall.html" in [t.name for t in response.templates]

        # Check context contains capture
        assert "capture" in response.context
        assert response.context["capture"] == self.capture

    def test_waterfall_view_capture_not_found_404(self) -> None:
        """Test that non-existent capture returns 404."""
        self.client.force_login(self.user)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        fake_url = reverse(
            "visualizations:waterfall",
            kwargs={"capture_uuid": fake_uuid},
        )

        response = self.client.get(fake_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_waterfall_view_capture_not_owned_404(self) -> None:
        """Test that users cannot access captures they don't own."""
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        self.client.force_login(other_user)

        response = self.client.get(self.waterfall_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_waterfall_view_deleted_capture_404(self) -> None:
        """Test that deleted captures return 404."""
        self.client.force_login(self.user)

        # Soft delete the capture
        self.capture.soft_delete()

        response = self.client.get(self.waterfall_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_waterfall_view_context_data(self) -> None:
        """Test that the view provides correct context data."""
        self.client.force_login(self.user)

        response = self.client.get(self.waterfall_url)
        assert response.status_code == status.HTTP_200_OK

        context = response.context
        assert "capture" in context

        capture = context["capture"]
        assert capture.uuid == self.capture.uuid
        assert capture.capture_type == self.capture.capture_type
        assert capture.channel == self.capture.channel
        assert capture.owner == self.user
        assert capture.is_deleted is False


class WaterfallAPIViewTestCases(TestCase):
    """Test cases for WaterfallAPIView."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        # Create test capture
        self.capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            index_name="test-index",
            owner=self.user,
            top_level_dir="/test/dir",
        )

        # Set up URL
        self.create_waterfall_url = reverse(
            "api:visualizations-create-waterfall",
            kwargs={"pk": self.capture.uuid},
        )

        self.get_waterfall_status_url = reverse(
            "api:visualizations-get-waterfall-status",
            kwargs={"pk": self.capture.uuid},
        )

        self.download_waterfall_url = reverse(
            "api:visualizations-download-waterfall",
            kwargs={"pk": self.capture.uuid},
        )

        self.get_waterfall_metadata_url = reverse(
            "api:visualizations-get-waterfall-metadata",
            kwargs={"pk": self.capture.uuid},
        )

    def test_create_waterfall_api_requires_authentication(self) -> None:
        """Test that create_waterfall API requires authentication."""
        response = self.client.post(self.create_waterfall_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_waterfall_api_authenticated_user_success(self) -> None:
        """Test that authenticated users can create waterfall processing via API."""
        self.client.force_login(self.user)

        with patch(
            "sds_gateway.visualizations.api_views.launch_visualization_processing"
        ) as mock_launch_processing:
            # Mock the return value to include the processed_data_id
            mock_launch_processing.return_value = {
                "status": "success",
                "message": "Waterfall processing started",
                "capture_uuid": str(self.capture.uuid),
                "processing_config": {
                    "waterfall": {
                        "processed_data_id": "test-uuid-123",
                    }
                },
            }

            response = self.client.post(self.create_waterfall_url)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "uuid" in data
            assert data["uuid"] == "test-uuid-123"

            # Verify processing was started
            mock_launch_processing.assert_called_once()

    def test_create_waterfall_api_capture_not_found(self) -> None:
        """Test that non-existent capture returns 404 for API."""
        self.client.force_login(self.user)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        fake_url = reverse(
            "api:visualizations-create-waterfall",
            kwargs={"pk": fake_uuid},
        )

        response = self.client.post(fake_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_waterfall_api_capture_not_owned(self) -> None:
        """Test that users cannot create waterfall for others' captures via API."""
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        self.client.force_login(other_user)

        response = self.client.post(self.create_waterfall_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_waterfall_api_existing_completed(self) -> None:
        """Test that existing completed waterfall is returned via API."""
        self.client.force_login(self.user)

        # Create existing completed waterfall
        existing_waterfall = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={},
        )

        response = self.client.post(self.create_waterfall_url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["uuid"] == str(existing_waterfall.uuid)
        assert data["processing_status"] == ProcessingStatus.Completed.value

    def test_get_waterfall_status_api_requires_authentication(self) -> None:
        """Test that get_waterfall_status API requires authentication."""
        response = self.client.get(self.get_waterfall_status_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_waterfall_status_api_missing_job_id(self) -> None:
        """Test that missing job_id parameter returns 400 for API."""
        self.client.force_login(self.user)

        response = self.client.get(self.get_waterfall_status_url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        data = response.json()
        assert "error" in data
        assert "job_id parameter is required" in data["error"]

    def test_get_waterfall_status_api_success(self) -> None:
        """Test successful waterfall status retrieval via API."""
        self.client.force_login(self.user)

        # Create waterfall processing job
        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Processing.value,
            metadata={},
        )

        response = self.client.get(
            self.get_waterfall_status_url, {"job_id": str(waterfall_data.uuid)}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["uuid"] == str(waterfall_data.uuid)
        assert data["processing_status"] == ProcessingStatus.Processing.value
        assert data["capture"] == str(self.capture.uuid)

    def test_download_waterfall_api_requires_authentication(self) -> None:
        """Test that download_waterfall API requires authentication."""
        response = self.client.get(self.download_waterfall_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_download_waterfall_api_missing_job_id(self) -> None:
        """Test that missing job_id parameter returns 400 for API."""
        self.client.force_login(self.user)

        response = self.client.get(self.download_waterfall_url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        data = response.json()
        assert "error" in data
        assert "job_id parameter is required" in data["error"]

    def test_download_waterfall_api_success(self) -> None:
        """Test successful waterfall download via API."""
        self.client.force_login(self.user)

        # Create test file content
        test_content = json.dumps({"test": "waterfall_data"})
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        # Create completed waterfall with data file
        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={},
            data_file=test_file,
        )

        response = self.client.get(
            self.download_waterfall_url, {"job_id": str(waterfall_data.uuid)}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.get("Content-Type") == "application/json"
        assert "attachment" in response.get("Content-Disposition", "")
        content_disposition = response.get("Content-Disposition", "")
        assert f"waterfall_{self.capture.uuid}.json" in content_disposition

        # Verify file content
        content = b"".join(response.streaming_content).decode()
        assert content == test_content

    def test_get_waterfall_metadata_api_requires_authentication(self) -> None:
        """Test that get_waterfall_metadata API requires authentication."""
        response = self.client.get(self.get_waterfall_metadata_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_waterfall_metadata_api_missing_job_id(self) -> None:
        """Test that missing job_id parameter returns 400 for API."""
        self.client.force_login(self.user)

        response = self.client.get(self.get_waterfall_metadata_url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        data = response.json()
        assert "error" in data
        assert "job_id parameter is required" in data["error"]

    def test_get_waterfall_metadata_api_success_with_existing_metadata(self) -> None:
        """Test successful waterfall metadata retrieval with existing metadata."""
        self.client.force_login(self.user)

        # Create test file content (array of slices)
        test_slices = [{"freq": i, "data": [1, 2, 3]} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        # Create completed waterfall with metadata already set
        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10, "sample_rate": 1000000},
            data_file=test_file,
        )

        response = self.client.get(
            self.get_waterfall_metadata_url,
            {"job_id": str(waterfall_data.uuid)},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["total_slices"] == 10
        assert data["sample_rate"] == 1000000

    def test_get_waterfall_metadata_api_calculates_slices_from_file(self) -> None:
        """Test that metadata slices are calculated from file if not present."""
        self.client.force_login(self.user)

        # Create test file content (array of slices)
        test_slices = [{"freq": i, "data": [1, 2, 3]} for i in range(15)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        # Create completed waterfall without total_slices in metadata
        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"sample_rate": 1000000},  # No total_slices
            data_file=test_file,
        )

        response = self.client.get(
            self.get_waterfall_metadata_url,
            {"job_id": str(waterfall_data.uuid)},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["slices_processed"] == 15
        assert data["sample_rate"] == 1000000

        # Verify that the metadata was saved back to the object
        waterfall_data.refresh_from_db()
        assert waterfall_data.metadata["slices_processed"] == 15

    def test_get_waterfall_metadata_api_job_not_found(self) -> None:
        """Test that non-existent job returns 404."""
        self.client.force_login(self.user)

        fake_job_id = "00000000-0000-0000-0000-000000000000"
        response = self.client.get(
            self.get_waterfall_metadata_url, {"job_id": fake_job_id}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_get_waterfall_metadata_api_processing_not_completed(self) -> None:
        """Test that incomplete processing returns 400."""
        self.client.force_login(self.user)

        # Create waterfall processing job that's still processing
        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Processing.value,
            metadata={},
        )

        response = self.client.get(
            self.get_waterfall_metadata_url,
            {"job_id": str(waterfall_data.uuid)},
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert "Waterfall processing not completed" in data["error"]

    def test_get_waterfall_metadata_api_capture_not_owned(self) -> None:
        """Test that users cannot get metadata for others' captures."""
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        self.client.force_login(self.user)

        # Create waterfall data for other user's capture
        other_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            index_name="other-index",
            owner=other_user,
            top_level_dir="/other/dir",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=other_capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10},
        )

        other_capture_url = reverse(
            "api:visualizations-get-waterfall-metadata",
            kwargs={"pk": other_capture.uuid},
        )

        response = self.client.get(
            other_capture_url, {"job_id": str(waterfall_data.uuid)}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_waterfall_api_with_start_index(self) -> None:
        """Test download_waterfall with start_index parameter."""
        self.client.force_login(self.user)

        # Create test file content with multiple slices
        test_slices = [
            {"index": i, "data": [i * 10 + j for j in range(5)]} for i in range(20)
        ]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 20},
            data_file=test_file,
        )

        # Request slices from index 5 to the end
        response = self.client.get(
            self.download_waterfall_url,
            {"job_id": str(waterfall_data.uuid), "start_index": 5},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "data" in data
        assert "start_index" in data
        assert "end_index" in data
        assert "total_slices" in data
        assert "count" in data

        assert data["start_index"] == 5
        assert data["end_index"] == 20
        assert data["total_slices"] == 20
        assert data["count"] == 15
        assert len(data["data"]) == 15
        assert data["data"][0]["index"] == 5
        assert data["data"][-1]["index"] == 19

    def test_download_waterfall_api_with_end_index(self) -> None:
        """Test download_waterfall with end_index parameter."""
        self.client.force_login(self.user)

        # Create test file content with multiple slices
        test_slices = [
            {"index": i, "data": [i * 10 + j for j in range(5)]} for i in range(20)
        ]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 20},
            data_file=test_file,
        )

        # Request slices from start to index 10
        response = self.client.get(
            self.download_waterfall_url,
            {"job_id": str(waterfall_data.uuid), "end_index": 10},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["start_index"] == 0
        assert data["end_index"] == 10
        assert data["total_slices"] == 20
        assert data["count"] == 10
        assert len(data["data"]) == 10
        assert data["data"][0]["index"] == 0
        assert data["data"][-1]["index"] == 9

    def test_download_waterfall_api_with_range(self) -> None:
        """Test download_waterfall with both start_index and end_index."""
        self.client.force_login(self.user)

        # Create test file content with multiple slices
        test_slices = [
            {"index": i, "data": [i * 10 + j for j in range(5)]} for i in range(20)
        ]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 20},
            data_file=test_file,
        )

        # Request slices from index 5 to 15
        response = self.client.get(
            self.download_waterfall_url,
            {
                "job_id": str(waterfall_data.uuid),
                "start_index": 5,
                "end_index": 15,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["start_index"] == 5
        assert data["end_index"] == 15
        assert data["total_slices"] == 20
        assert data["count"] == 10
        assert len(data["data"]) == 10
        assert data["data"][0]["index"] == 5
        assert data["data"][-1]["index"] == 14

    def test_download_waterfall_api_invalid_range_start_greater_than_end(self) -> None:
        """Test that start_index > end_index returns 400."""
        self.client.force_login(self.user)

        # Create test file content
        test_slices = [{"index": i} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10},
            data_file=test_file,
        )

        response = self.client.get(
            self.download_waterfall_url,
            {
                "job_id": str(waterfall_data.uuid),
                "start_index": 7,
                "end_index": 5,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert "start_index must be less than or equal to end_index" in data["error"]

    def test_download_waterfall_api_start_index_out_of_bounds(self) -> None:
        """Test that start_index >= total_slices returns 400."""
        self.client.force_login(self.user)

        # Create test file content
        test_slices = [{"index": i} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10},
            data_file=test_file,
        )

        response = self.client.get(
            self.download_waterfall_url,
            {
                "job_id": str(waterfall_data.uuid),
                "start_index": 10,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert "start_index 10 is out of range" in data["error"]
        assert "Total slices: 10" in data["error"]

    def test_download_waterfall_api_negative_indices(self) -> None:
        """Test that negative indices return 400."""
        self.client.force_login(self.user)

        # Create test file content
        test_slices = [{"index": i} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10},
            data_file=test_file,
        )

        response = self.client.get(
            self.download_waterfall_url,
            {
                "job_id": str(waterfall_data.uuid),
                "start_index": -1,
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert "must be non-negative" in data["error"]

    def test_download_waterfall_api_invalid_index_type(self) -> None:
        """Test that non-integer indices return 400."""
        self.client.force_login(self.user)

        # Create test file content
        test_slices = [{"index": i} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10},
            data_file=test_file,
        )

        response = self.client.get(
            self.download_waterfall_url,
            {
                "job_id": str(waterfall_data.uuid),
                "start_index": "not_a_number",
            },
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert "Must be integers" in data["error"]

    def test_download_waterfall_api_end_index_clamped_to_total(self) -> None:
        """Test that end_index is clamped to total_slices."""
        self.client.force_login(self.user)

        # Create test file content
        test_slices = [{"index": i} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={"total_slices": 10},
            data_file=test_file,
        )

        # Request end_index beyond total_slices
        response = self.client.get(
            self.download_waterfall_url,
            {
                "job_id": str(waterfall_data.uuid),
                "start_index": 5,
                "end_index": 20,
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["start_index"] == 5
        assert data["end_index"] == 10  # Clamped to total_slices
        assert data["total_slices"] == 10
        assert data["count"] == 5
        assert len(data["data"]) == 5

    def test_download_waterfall_api_backward_compatibility_no_params(self) -> None:
        """Test that download_waterfall without range params returns full file."""
        self.client.force_login(self.user)

        # Create test file content
        test_slices = [{"index": i} for i in range(10)]
        test_content = json.dumps(test_slices)
        test_file = SimpleUploadedFile(
            "waterfall_test.json",
            test_content.encode(),
            content_type="application/json",
        )

        waterfall_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Waterfall.value,
            processing_parameters={},
            processing_status=ProcessingStatus.Completed.value,
            metadata={},
            data_file=test_file,
        )

        # Request without range parameters (backward compatibility)
        response = self.client.get(
            self.download_waterfall_url,
            {"job_id": str(waterfall_data.uuid)},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.get("Content-Type") == "application/json"
        assert "attachment" in response.get("Content-Disposition", "")

        # Verify it returns the full file content (not JSON response)
        content = b"".join(response.streaming_content).decode()
        assert content == test_content


class SpectrogramVisualizationViewTestCases(TestCase):
    """Test cases for SpectrogramVisualizationView."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        # Create test capture
        self.capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            index_name="test-index",
            owner=self.user,
            top_level_dir="/test/dir",
        )

        # Set up URL
        self.spectrogram_url = reverse(
            "visualizations:spectrogram",
            kwargs={"capture_uuid": self.capture.uuid},
        )

    def test_spectrogram_view_requires_login(self) -> None:
        """Test that the spectrogram view requires login."""
        response = self.client.get(self.spectrogram_url)
        assert response.status_code == status.HTTP_302_FOUND  # Redirect to login

        # Follow redirect to confirm it's going to login
        login_url = response.url
        assert "login" in login_url

    def test_spectrogram_view_with_authenticated_user_200(self) -> None:
        """Test that authenticated users can access the spectrogram view."""
        self.client.force_login(self.user)

        response = self.client.get(self.spectrogram_url)
        assert response.status_code == status.HTTP_200_OK

        # Check template is used
        assert "visualizations/spectrogram.html" in [t.name for t in response.templates]

        # Check context contains capture
        assert "capture" in response.context
        assert response.context["capture"] == self.capture

    def test_spectrogram_view_capture_not_found_404(self) -> None:
        """Test that non-existent capture returns 404."""
        self.client.force_login(self.user)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        fake_url = reverse(
            "visualizations:spectrogram",
            kwargs={"capture_uuid": fake_uuid},
        )

        response = self.client.get(fake_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_spectrogram_view_capture_not_owned_404(self) -> None:
        """Test that users cannot access captures they don't own."""
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        self.client.force_login(other_user)

        response = self.client.get(self.spectrogram_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_spectrogram_view_deleted_capture_404(self) -> None:
        """Test that deleted captures return 404."""
        self.client.force_login(self.user)

        # Soft delete the capture
        self.capture.soft_delete()

        response = self.client.get(self.spectrogram_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_spectrogram_view_context_data(self) -> None:
        """Test that the view provides correct context data."""
        self.client.force_login(self.user)

        response = self.client.get(self.spectrogram_url)
        assert response.status_code == status.HTTP_200_OK

        context = response.context
        assert "capture" in context

        capture = context["capture"]
        assert capture.uuid == self.capture.uuid
        assert capture.capture_type == self.capture.capture_type
        assert capture.channel == self.capture.channel
        assert capture.owner == self.user
        assert capture.is_deleted is False


class SpectrogramAPIViewTestCases(TestCase):
    """Test cases for SpectrogramAPIView."""

    def setUp(self) -> None:
        """Set up test data."""
        self.user = User.objects.create(
            email="testuser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        # Create test capture
        self.capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="ch0",
            index_name="test-index",
            owner=self.user,
            top_level_dir="/test/dir",
        )

        # Set up URLs
        self.create_spectrogram_url = reverse(
            "api:visualizations-create-spectrogram",
            kwargs={"pk": self.capture.uuid},
        )

        self.get_spectrogram_status_url = reverse(
            "api:visualizations-get-spectrogram-status",
            kwargs={"pk": self.capture.uuid},
        )

        self.download_spectrogram_url = reverse(
            "api:visualizations-download-spectrogram",
            kwargs={"pk": self.capture.uuid},
        )

    def test_create_spectrogram_api_requires_authentication(self) -> None:
        """Test that create_spectrogram API requires authentication."""
        response = self.client.post(self.create_spectrogram_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_spectrogram_api_authenticated_user_success(self) -> None:
        """Test that authenticated users can create spectrogram processing via API."""
        self.client.force_login(self.user)

        with patch(
            "sds_gateway.visualizations.api_views.launch_visualization_processing"
        ) as mock_launch_processing:
            # Mock the return value to include the processed_data_id
            mock_launch_processing.return_value = {
                "status": "success",
                "message": "Spectrogram processing started",
                "capture_uuid": str(self.capture.uuid),
                "processing_config": {
                    "spectrogram": {
                        "processed_data_id": "test-uuid-123",
                        "fft_size": 1024,
                        "std_dev": 100,
                        "hop_size": 500,
                        "colormap": "magma",
                    }
                },
            }

            response = self.client.post(
                self.create_spectrogram_url,
                {
                    "fft_size": 1024,
                    "std_dev": 100,
                    "hop_size": 500,
                    "colormap": "magma",
                },
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "uuid" in data
            assert data["uuid"] == "test-uuid-123"

            # Verify processing was started
            mock_launch_processing.assert_called_once()

    def test_create_spectrogram_api_capture_not_found(self) -> None:
        """Test that non-existent capture returns 404 for API."""
        self.client.force_login(self.user)

        fake_uuid = "00000000-0000-0000-0000-000000000000"
        fake_url = reverse(
            "api:visualizations-create-spectrogram",
            kwargs={"pk": fake_uuid},
        )

        response = self.client.post(fake_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_spectrogram_api_capture_not_owned(self) -> None:
        """Test that users cannot create spectrogram for others' captures via API."""
        other_user = User.objects.create(
            email="otheruser@example.com",
            password="testpassword",  # noqa: S106
            is_approved=True,
        )

        self.client.force_login(other_user)

        response = self.client.post(self.create_spectrogram_url)
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_create_spectrogram_api_existing_completed(self) -> None:
        """Test that existing completed spectrogram is returned via API."""
        self.client.force_login(self.user)

        # Create existing completed spectrogram
        existing_spectrogram = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Spectrogram.value,
            processing_parameters={
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
            processing_status=ProcessingStatus.Completed.value,
            metadata={},
        )

        response = self.client.post(
            self.create_spectrogram_url,
            {
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["uuid"] == str(existing_spectrogram.uuid)
        assert data["processing_status"] == ProcessingStatus.Completed.value

    def test_create_spectrogram_api_invalid_parameters(self) -> None:
        """Test that invalid spectrogram parameters return 400."""
        self.client.force_login(self.user)

        # Test invalid FFT size (not power of 2)
        response = self.client.post(
            self.create_spectrogram_url,
            {
                "fft_size": 1000,  # Not a power of 2
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        # Test invalid colormap
        response = self.client.post(
            self.create_spectrogram_url,
            {
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "invalid_colormap",
            },
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_get_spectrogram_status_api_requires_authentication(self) -> None:
        """Test that get_spectrogram_status API requires authentication."""
        response = self.client.get(self.get_spectrogram_status_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_get_spectrogram_status_api_missing_job_id(self) -> None:
        """Test that missing job_id parameter returns 400 for API."""
        self.client.force_login(self.user)

        response = self.client.get(self.get_spectrogram_status_url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        data = response.json()
        assert "error" in data
        assert "job_id parameter is required" in data["error"]

    def test_get_spectrogram_status_api_success(self) -> None:
        """Test successful spectrogram status retrieval via API."""
        self.client.force_login(self.user)

        # Create spectrogram processing job
        spectrogram_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Spectrogram.value,
            processing_parameters={
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
            processing_status=ProcessingStatus.Processing.value,
            metadata={},
        )

        response = self.client.get(
            self.get_spectrogram_status_url, {"job_id": str(spectrogram_data.uuid)}
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["uuid"] == str(spectrogram_data.uuid)
        assert data["processing_status"] == ProcessingStatus.Processing.value
        assert data["capture"] == str(self.capture.uuid)

    def test_get_spectrogram_status_api_job_not_found(self) -> None:
        """Test that non-existent job returns 404."""
        self.client.force_login(self.user)

        fake_job_id = "00000000-0000-0000-0000-000000000000"
        response = self.client.get(
            self.get_spectrogram_status_url, {"job_id": fake_job_id}
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_download_spectrogram_api_requires_authentication(self) -> None:
        """Test that download_spectrogram API requires authentication."""
        response = self.client.get(self.download_spectrogram_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_download_spectrogram_api_missing_job_id(self) -> None:
        """Test that missing job_id parameter returns 400 for API."""
        self.client.force_login(self.user)

        response = self.client.get(self.download_spectrogram_url)
        assert response.status_code == status.HTTP_400_BAD_REQUEST

        data = response.json()
        assert "error" in data
        assert "job_id parameter is required" in data["error"]

    def test_download_spectrogram_api_processing_not_completed(self) -> None:
        """Test that incomplete processing returns 400."""
        self.client.force_login(self.user)

        # Create spectrogram processing job that's still processing
        spectrogram_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Spectrogram.value,
            processing_parameters={
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
            processing_status=ProcessingStatus.Processing.value,
            metadata={},
        )

        response = self.client.get(
            self.download_spectrogram_url, {"job_id": str(spectrogram_data.uuid)}
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "error" in data
        assert "Spectrogram processing not completed" in data["error"]

    def test_download_spectrogram_api_no_file(self) -> None:
        """Test that missing data file returns 404."""
        self.client.force_login(self.user)

        # Create completed spectrogram without data file
        spectrogram_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Spectrogram.value,
            processing_parameters={
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
            processing_status=ProcessingStatus.Completed.value,
            metadata={},
        )

        response = self.client.get(
            self.download_spectrogram_url, {"job_id": str(spectrogram_data.uuid)}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "error" in data
        assert "No spectrogram file found" in data["error"]

    def test_download_spectrogram_api_success(self) -> None:
        """Test successful spectrogram download via API."""
        self.client.force_login(self.user)

        # Create test file content (PNG image)
        test_content = b"fake_png_content"
        test_file = SimpleUploadedFile(
            "spectrogram_test.png",
            test_content,
            content_type="image/png",
        )

        # Create completed spectrogram with data file
        spectrogram_data = PostProcessedData.objects.create(
            capture=self.capture,
            processing_type=ProcessingType.Spectrogram.value,
            processing_parameters={
                "fft_size": 1024,
                "std_dev": 100,
                "hop_size": 500,
                "colormap": "magma",
            },
            processing_status=ProcessingStatus.Completed.value,
            metadata={},
            data_file=test_file,
        )

        response = self.client.get(
            self.download_spectrogram_url, {"job_id": str(spectrogram_data.uuid)}
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.get("Content-Type") == "image/png"
        assert "attachment" in response.get("Content-Disposition", "")
        content_disposition = response.get("Content-Disposition", "")
        assert f"spectrogram_{self.capture.uuid}.png" in content_disposition

        # Verify file content
        content = b"".join(response.streaming_content)
        assert content == test_content
