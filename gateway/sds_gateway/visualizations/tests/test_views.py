"""Tests for visualization views."""

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework import status

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType

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

        other_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="other-channel",
            index_name="other-index",
            owner=other_user,
            top_level_dir="/other/dir",
        )

        self.client.force_login(self.user)

        other_url = reverse(
            "visualizations:waterfall",
            kwargs={"capture_uuid": other_capture.uuid},
        )

        response = self.client.get(other_url)
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


@pytest.mark.skipif(
    not settings.EXPERIMENTAL_SPECTROGRAM, reason="Spectrogram feature is not enabled"
)
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

        other_capture = Capture.objects.create(
            capture_type=CaptureType.DigitalRF,
            channel="other-channel",
            index_name="other-index",
            owner=other_user,
            top_level_dir="/other/dir",
        )

        self.client.force_login(self.user)

        other_url = reverse(
            "visualizations:spectrogram",
            kwargs={"capture_uuid": other_capture.uuid},
        )

        response = self.client.get(other_url)
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
