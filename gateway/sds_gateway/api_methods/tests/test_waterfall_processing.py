"""Tests for waterfall processing functionality."""

import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test import override_settings

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import WaterfallData
from sds_gateway.api_methods.tasks import process_capture_waterfall

User = get_user_model()


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    MEDIA_ROOT=tempfile.mkdtemp(),
)
class TestWaterfallProcessing(TestCase):
    """Test waterfall processing functionality."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            is_approved=True,
        )

        self.capture = Capture.objects.create(
            channel="test_channel",
            capture_type=CaptureType.DigitalRF,
            top_level_dir="/files/test@example.com/captures/test_capture/",
            owner=self.user,
            name="Test DigitalRF Capture",
        )

    def test_waterfall_data_model_creation(self):
        """Test creating a WaterfallData model instance."""
        waterfall_data = WaterfallData.objects.create(
            capture=self.capture,
            center_frequency=1000000000.0,  # 1 GHz
            sample_rate=2000000.0,  # 2 MHz
            min_frequency=999000000.0,  # 999 MHz
            max_frequency=1001000000.0,  # 1001 MHz
            fft_size=1024,
            samples_per_slice=1024,
            total_slices=100,
            processing_status="completed",
        )

        self.assertEqual(waterfall_data.capture, self.capture)
        self.assertEqual(waterfall_data.center_frequency, 1000000000.0)
        self.assertEqual(waterfall_data.processing_status, "completed")
        self.assertTrue(waterfall_data.is_ready)

    def test_waterfall_data_status_methods(self):
        """Test WaterfallData status methods."""
        waterfall_data = WaterfallData.objects.create(
            capture=self.capture,
            center_frequency=1000000000.0,
            sample_rate=2000000.0,
            min_frequency=999000000.0,
            max_frequency=1001000000.0,
            fft_size=1024,
            samples_per_slice=1024,
            total_slices=100,
        )

        # Test initial state
        self.assertEqual(waterfall_data.processing_status, "pending")
        self.assertFalse(waterfall_data.is_ready)

        # Test marking as processing
        waterfall_data.mark_processing_started()
        self.assertEqual(waterfall_data.processing_status, "processing")

        # Test marking as completed
        waterfall_data.mark_processing_completed()
        self.assertEqual(waterfall_data.processing_status, "completed")
        self.assertTrue(waterfall_data.is_ready)
        self.assertIsNotNone(waterfall_data.processed_at)

    def test_waterfall_data_error_handling(self):
        """Test WaterfallData error handling."""
        waterfall_data = WaterfallData.objects.create(
            capture=self.capture,
            center_frequency=1000000000.0,
            sample_rate=2000000.0,
            min_frequency=999000000.0,
            max_frequency=1001000000.0,
            fft_size=1024,
            samples_per_slice=1024,
            total_slices=100,
        )

        error_message = "Test error message"
        waterfall_data.mark_processing_failed(error_message)

        self.assertEqual(waterfall_data.processing_status, "failed")
        self.assertEqual(waterfall_data.processing_error, error_message)
        self.assertFalse(waterfall_data.is_ready)

    @patch("sds_gateway.api_methods.tasks._process_digitalrf_waterfall")
    def test_process_capture_waterfall_task_success(self, mock_process):
        """Test successful waterfall processing task."""
        # Mock successful processing
        mock_process.return_value = {
            "status": "success",
            "message": "Waterfall data processed successfully",
            "capture_uuid": str(self.capture.uuid),
            "waterfall_uuid": "test-uuid",
            "total_slices": 100,
        }

        # Run the task
        result = process_capture_waterfall(str(self.capture.uuid))

        # Verify the result
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["capture_uuid"], str(self.capture.uuid))

        # Verify waterfall data was created
        waterfall_data = WaterfallData.objects.filter(capture=self.capture).first()
        self.assertIsNotNone(waterfall_data)
        self.assertEqual(waterfall_data.processing_status, "completed")

    @patch("sds_gateway.api_methods.tasks._process_digitalrf_waterfall")
    def test_process_capture_waterfall_task_failure(self, mock_process):
        """Test failed waterfall processing task."""
        # Mock failed processing
        mock_process.return_value = {
            "status": "error",
            "message": "Processing failed",
        }

        # Run the task
        result = process_capture_waterfall(str(self.capture.uuid))

        # Verify the result
        self.assertEqual(result["status"], "error")
        self.assertIn("Processing failed", result["message"])

        # Verify waterfall data was marked as failed
        waterfall_data = WaterfallData.objects.filter(capture=self.capture).first()
        self.assertIsNotNone(waterfall_data)
        self.assertEqual(waterfall_data.processing_status, "failed")

    def test_process_capture_waterfall_invalid_capture_type(self):
        """Test waterfall processing with non-DigitalRF capture."""
        # Create a non-DigitalRF capture
        non_drf_capture = Capture.objects.create(
            channel="test_channel",
            capture_type=CaptureType.RadioHound,
            top_level_dir="/files/test@example.com/captures/test_rh_capture/",
            owner=self.user,
            name="Test RadioHound Capture",
        )

        # Run the task
        result = process_capture_waterfall(str(non_drf_capture.uuid))

        # Verify the result
        self.assertEqual(result["status"], "error")
        self.assertIn("not a DigitalRF capture", result["message"])

    def test_process_capture_waterfall_nonexistent_capture(self):
        """Test waterfall processing with nonexistent capture."""
        # Run the task with a nonexistent UUID
        result = process_capture_waterfall("00000000-0000-0000-0000-000000000000")

        # Verify the result
        self.assertEqual(result["status"], "error")
        self.assertIn("not found", result["message"])

    def test_waterfall_data_unique_constraint(self):
        """Test that waterfall data has unique constraint on capture and processing parameters."""
        # Create first waterfall data
        WaterfallData.objects.create(
            capture=self.capture,
            center_frequency=1000000000.0,
            sample_rate=2000000.0,
            min_frequency=999000000.0,
            max_frequency=1001000000.0,
            fft_size=1024,
            samples_per_slice=1024,
            total_slices=100,
        )

        # Try to create another with same parameters (should fail)
        with self.assertRaises(Exception):  # IntegrityError or similar
            WaterfallData.objects.create(
                capture=self.capture,
                center_frequency=1000000000.0,
                sample_rate=2000000.0,
                min_frequency=999000000.0,
                max_frequency=1001000000.0,
                fft_size=1024,
                samples_per_slice=1024,
                total_slices=100,
            )

        # Create with different parameters (should succeed)
        WaterfallData.objects.create(
            capture=self.capture,
            center_frequency=1000000000.0,
            sample_rate=2000000.0,
            min_frequency=999000000.0,
            max_frequency=1001000000.0,
            fft_size=2048,  # Different FFT size
            samples_per_slice=1024,
            total_slices=100,
        )

        # Should have 2 waterfall data records
        self.assertEqual(WaterfallData.objects.filter(capture=self.capture).count(), 2)
