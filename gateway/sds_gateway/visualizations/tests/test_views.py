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

    def test_create_waterfall_api_requires_authentication(self) -> None:
        """Test that create_waterfall API requires authentication."""
        response = self.client.post(self.create_waterfall_url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_waterfall_api_authenticated_user_success(self) -> None:
        """Test that authenticated users can create waterfall processing via API."""
        self.client.force_login(self.user)

        with patch(
            "sds_gateway.visualizations.api_views.VisualizationViewSet._start_waterfall_processing"
        ) as mock_start_processing:
            response = self.client.post(self.create_waterfall_url)

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert "uuid" in data
            assert data["processing_type"] == ProcessingType.Waterfall.value
            assert data["processing_status"] == ProcessingStatus.Pending.value
            assert data["capture"] == str(self.capture.uuid)

            # Verify PostProcessedData was created
            waterfall_data = PostProcessedData.objects.get(uuid=data["uuid"])
            assert waterfall_data.capture == self.capture
            assert waterfall_data.processing_type == ProcessingType.Waterfall.value
            assert waterfall_data.processing_status == ProcessingStatus.Pending.value

            # Verify processing was started
            mock_start_processing.assert_called_once_with(waterfall_data)

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
