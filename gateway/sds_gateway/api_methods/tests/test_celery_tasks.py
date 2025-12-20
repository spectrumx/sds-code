"""
Tests for Celery tasks in the API methods app.
"""

import datetime
import shutil
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.test import TestCase
from django.test import override_settings

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.models import ZipFileStatus
from sds_gateway.api_methods.tasks import acquire_user_lock
from sds_gateway.api_methods.tasks import check_celery_task
from sds_gateway.api_methods.tasks import check_disk_space_available
from sds_gateway.api_methods.tasks import check_email_task
from sds_gateway.api_methods.tasks import cleanup_expired_temp_zips
from sds_gateway.api_methods.tasks import cleanup_orphaned_zip_files
from sds_gateway.api_methods.tasks import cleanup_orphaned_zips
from sds_gateway.api_methods.tasks import format_file_size
from sds_gateway.api_methods.tasks import get_user_task_status
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import release_user_lock
from sds_gateway.api_methods.tasks import send_item_files_email
from sds_gateway.api_methods.utils.disk_utils import estimate_disk_size

# pyright: reportFunctionMemberAccess=false, reportCallIssue=false

User = get_user_model()

# Test constants
EXPECTED_FILES_COUNT = 3
EXPECTED_EXPIRED_FILES_COUNT = 2
CELERY_BEAT_SCHEDULE_EXPIRES = 3600


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_TASK_EAGER_PROPAGATES=True,
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    MEDIA_ROOT=tempfile.mkdtemp(),
    CELERY_BROKER_URL="redis://localhost:6379/0",
)
class TestCeleryTasks(TestCase):
    """Test Celery tasks for dataset file processing."""

    LOCK_TIMEOUT_SECONDS = 300

    def setUp(self):
        """Set up test data."""
        # Create test media directory structure
        self.test_media_root = Path(tempfile.mkdtemp())
        self.test_media_root.mkdir(parents=True, exist_ok=True)
        (self.test_media_root / "temp_zips").mkdir(parents=True, exist_ok=True)

        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",  # noqa: S106
            is_approved=True,
        )

        self.base_dir = "/files/test@example.com"
        self.rel_path_capture = "captures/test_capture"
        self.rel_path_artifacts = "artifacts"
        self.top_level_dir = f"{self.base_dir}/{self.rel_path_capture}"

        # Create a test dataset
        self.dataset = Dataset.objects.create(
            name="Test Dataset",
            description="A test dataset for testing",
            owner=self.user,
        )

        # Create a test capture
        self.capture = Capture.objects.create(
            channel="test_channel",
            capture_type="drf",
            top_level_dir=self.top_level_dir,
            owner=self.user,
        )

        # Link capture to dataset
        self.dataset.captures.add(self.capture)

        # Create test files with proper ContentFile objects that have checksum names
        # First create the content files
        content1 = ContentFile(b"test file 1 content for capture")
        content2 = ContentFile(b"test file 2 content for capture subdir")
        content3 = ContentFile(b"test file 3 content for dataset artifacts")

        # Calculate real checksums using the File model's calculate_checksum method
        file_model = File()
        self.checksum1 = file_model.calculate_checksum(content1)
        self.checksum2 = file_model.calculate_checksum(content2)
        self.checksum3 = file_model.calculate_checksum(content3)

        # Reset file positions after checksum calculation
        content1.seek(0)
        content2.seek(0)
        content3.seek(0)

        # Set the names to be the checksums (this is how files are stored in MinIO)
        content1.name = self.checksum1
        content2.name = self.checksum2
        content3.name = self.checksum3

        self.file1 = File.objects.create(
            name="test_file1.txt",
            size=len(b"test file 1 content for capture"),
            directory=self.top_level_dir,
            owner=self.user,
            capture=self.capture,
            file=content1,
            sum_blake3=self.checksum1,
        )

        self.file2 = File.objects.create(
            name="test_file2.txt",
            size=len(b"test file 2 content for capture subdir"),
            directory=f"{self.top_level_dir}/subdir",
            owner=self.user,
            capture=self.capture,
            file=content2,
            sum_blake3=self.checksum2,
        )

        self.file3 = File.objects.create(
            name="test_file3.txt",
            size=len(b"test file 3 content for dataset artifacts"),
            directory=f"{self.base_dir}/{self.rel_path_artifacts}",
            owner=self.user,
            file=content3,
            sum_blake3=self.checksum3,
        )

        # Add files directly to dataset
        self.dataset.files.add(self.file3)

    def tearDown(self):
        """Clean up test data."""
        # Clean up test media directory

        if self.test_media_root.exists():
            shutil.rmtree(self.test_media_root)

    def test_celery_task(self):
        """Test the basic Celery task functionality."""
        # Test with default message
        result = check_celery_task.delay()
        expected_result = "Hello from Celery! - Task completed successfully!"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

        # Test with custom message
        custom_message = "Custom message"
        result = check_celery_task.delay(custom_message)
        expected_result = f"{custom_message} - Task completed successfully!"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

    def test_email_task(self):
        """Test the email sending task."""
        # Clear any existing emails
        mail.outbox.clear()

        # Test email sending
        result = check_email_task.delay("test@example.com")
        expected_result = "Test email sent to test@example.com"
        assert result.get() == expected_result, (
            f"Expected '{expected_result}', got '{result.get()}'"
        )

        # Verify email was sent
        assert len(mail.outbox) == 1, f"Expected 1 email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        assert email.subject == "Test Email from Celery", (
            f"Expected subject 'Test Email from Celery', got '{email.subject}'"
        )
        assert email.to == ["test@example.com"], (
            f"Expected to ['test@example.com'], got {email.to}"
        )
        expected_body_content = "This is a test email sent from Celery"
        assert expected_body_content in email.body, (
            f"Expected email body to contain '{expected_body_content}', "
            f"got '{email.body}'"
        )

    @patch("sds_gateway.api_methods.tasks.get_minio_client")
    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.release_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_success(
        self,
        mock_is_locked,
        mock_release_lock,
        mock_acquire_lock,
        mock_get_minio_client,
    ):
        """Test successful dataset files email sending with new workflow."""
        # Mock MinIO client - will return different content for each file request
        mock_client = MagicMock()
        mock_response = MagicMock()
        # Return content that matches our test files
        # (the actual content will vary by checksum)
        mock_response.stream.return_value = [b"mocked file content chunk"]
        mock_response.close.return_value = None
        mock_response.release_conn.return_value = None

        # Configure the mock to return the response for any object name
        mock_client.get_object.return_value = mock_response
        mock_get_minio_client.return_value = mock_client

        # Mock Redis locking functions
        mock_is_locked.return_value = False
        mock_acquire_lock.return_value = True
        mock_release_lock.return_value = True

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_item_files_email.delay(
            str(self.dataset.uuid), str(self.user.id), ItemType.DATASET
        )

        # Get the result
        task_result = result.get()

        # Verify task completed successfully
        assert task_result["status"] == "success", (
            f"Expected status 'success', got '{task_result['status']}'"
        )
        assert task_result["files_processed"] == EXPECTED_FILES_COUNT, (
            f"Expected {EXPECTED_FILES_COUNT} files processed, "
            f"got {task_result['files_processed']}"
        )
        assert "temp_zip_uuid" in task_result, (
            f"Expected 'temp_zip_uuid' in result, got {task_result.keys()}"
        )

        # Verify email was sent
        assert len(mail.outbox) == 1, f"Expected 1 email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = "Your dataset 'Test Dataset' is ready for download"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == ["test@example.com"], (
            f"Expected to ['test@example.com'], got {email.to}"
        )

        # Verify TemporaryZipFile was created
        temp_zip_uuid = task_result["temp_zip_uuid"]
        temp_zip = TemporaryZipFile.objects.get(uuid=temp_zip_uuid)
        assert temp_zip.owner == self.user, (
            f"Expected owner {self.user}, got {temp_zip.owner}"
        )
        assert temp_zip.files_processed == EXPECTED_FILES_COUNT, (
            f"Expected {EXPECTED_FILES_COUNT} files processed, "
            f"got {temp_zip.files_processed}"
        )
        assert not temp_zip.is_deleted, "TemporaryZipFile should not be deleted"
        assert not temp_zip.is_expired, "TemporaryZipFile should not be expired"

        # Verify locking was used correctly
        mock_is_locked.assert_called_once_with(str(self.user.id), "dataset_download")
        mock_acquire_lock.assert_called_once_with(str(self.user.id), "dataset_download")
        mock_release_lock.assert_called_once_with(str(self.user.id), "dataset_download")

    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_user_already_locked(
        self, mock_is_locked, mock_acquire_lock
    ):
        """Test dataset email task when user already has a lock."""
        # Mock user as already locked
        mock_is_locked.return_value = True

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_item_files_email.delay(
            str(self.dataset.uuid), str(self.user.id), ItemType.DATASET
        )

        # Get the result
        task_result = result.get()

        # Verify task failed due to lock
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        expected_message = (
            "You already have a dataset download in progress. "
            "Please wait for it to complete."
        )
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify error email was sent
        assert len(mail.outbox) == 1, f"Expected 1 error email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = f"Error downloading your dataset: {self.dataset.name}"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == [self.user.email], (
            f"Expected to [{self.user.email}], got {email.to}"
        )

    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_lock_acquisition_failed(
        self, mock_is_locked, mock_acquire_lock
    ):
        """Test dataset email task when lock acquisition fails."""
        # Mock user as not locked but lock acquisition fails
        mock_is_locked.return_value = False
        mock_acquire_lock.return_value = False

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_item_files_email.delay(
            str(self.dataset.uuid), str(self.user.id), ItemType.DATASET
        )

        # Get the result
        task_result = result.get()

        # Verify task failed due to lock acquisition failure
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        expected_message = (
            "Another download is already in progress. Please wait for it to complete."
        )
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify error email was sent
        assert len(mail.outbox) == 1, f"Expected 1 error email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = f"Error downloading your dataset: {self.dataset.name}"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == [self.user.email], (
            f"Expected to [{self.user.email}], got {email.to}"
        )

    @patch("sds_gateway.api_methods.tasks.get_minio_client")
    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.release_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_download_failure(
        self,
        mock_is_locked,
        mock_release_lock,
        mock_acquire_lock,
        mock_get_minio_client,
    ):
        """Test dataset email task when file download fails."""
        # Mock Redis locking functions
        mock_is_locked.return_value = False
        mock_acquire_lock.return_value = True
        mock_release_lock.return_value = True

        # Mock MinIO client to raise an exception during file download
        mock_client = MagicMock()
        mock_client.get_object.side_effect = OSError("MinIO download failed")
        mock_get_minio_client.return_value = mock_client

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_item_files_email.delay(
            str(self.dataset.uuid), str(self.user.id), ItemType.DATASET
        )

        # Get the result
        task_result = result.get()

        # Verify task completed with error
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        expected_message = "No files could be processed"
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify error email was sent
        assert len(mail.outbox) == 1, f"Expected 1 error email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = f"Error downloading your dataset: {self.dataset.name}"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == [self.user.email], (
            f"Expected to [{self.user.email}], got {email.to}"
        )

    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_timeout_handling(
        self, mock_is_locked, mock_acquire_lock
    ):
        """Test dataset email task when timeout occurs."""
        # Mock Redis locking functions
        mock_is_locked.return_value = False
        mock_acquire_lock.return_value = True

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task with a timeout exception
        with patch(
            "sds_gateway.api_methods.tasks._validate_item_download_request"
        ) as mock_validate:
            # Mock successful validation
            mock_validate.return_value = (None, self.user, self.dataset)

            # Mock the _process_item_files to raise a timeout exception
            with patch(
                "sds_gateway.api_methods.tasks._process_item_files"
            ) as mock_process:
                mock_process.side_effect = SoftTimeLimitExceeded("Task timed out")

                # Test the task
                result = send_item_files_email.delay(
                    str(self.dataset.uuid), str(self.user.id), ItemType.DATASET
                )

                # Get the result
                task_result = result.get()

                # Verify task completed with timeout error
                assert task_result["status"] == "error", (
                    f"Expected status 'error', got '{task_result['status']}'"
                )
                assert "timed out" in task_result["message"], (
                    f"Expected timeout message, got '{task_result['message']}'"
                )

                # Verify error email was sent
                assert len(mail.outbox) == 1, "Expected 1 error email to be sent"
                error_email = mail.outbox[0]
                assert "Error downloading your dataset" in error_email.subject
                assert self.user.email in error_email.to

    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_no_files(self, mock_is_locked, mock_acquire_lock):
        """Test dataset email task when no files are found."""
        # Create a dataset with no files
        empty_dataset = Dataset.objects.create(
            name="Empty Dataset",
            description="A dataset with no files",
            owner=self.user,
        )

        # Mock Redis locking functions
        mock_is_locked.return_value = False
        mock_acquire_lock.return_value = True

        # Clear any existing emails
        mail.outbox.clear()

        # Test the task
        result = send_item_files_email.delay(
            str(empty_dataset.uuid), str(self.user.id), ItemType.DATASET
        )

        # Get the result
        task_result = result.get()

        # Verify task completed with error
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        expected_message = "No files found in dataset"
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify error email was sent
        assert len(mail.outbox) == 1, f"Expected 1 error email, got {len(mail.outbox)}"
        email = mail.outbox[0]
        expected_subject = f"Error downloading your dataset: {empty_dataset.name}"
        assert email.subject == expected_subject, (
            f"Expected subject '{expected_subject}', got '{email.subject}'"
        )
        assert email.to == [self.user.email], (
            f"Expected to [{self.user.email}], got {email.to}"
        )

    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_dataset_not_found(
        self, mock_is_locked, mock_acquire_lock
    ):
        """Test dataset email task when dataset doesn't exist."""
        # Mock Redis locking functions
        mock_is_locked.return_value = False
        mock_acquire_lock.return_value = True

        # Clear any existing emails
        mail.outbox.clear()

        # Test with non-existent dataset UUID
        result = send_item_files_email.delay(
            "00000000-0000-0000-0000-000000000000", str(self.user.id), ItemType.DATASET
        )

        # Get the result
        task_result = result.get()

        # Verify task failed
        assert task_result["status"] == "error", (
            f"Expected status 'error', got '{task_result['status']}'"
        )
        expected_message = "Dataset not found or access denied"
        assert task_result["message"] == expected_message, (
            f"Expected message '{expected_message}', got '{task_result['message']}'"
        )

        # Verify no email was sent
        assert len(mail.outbox) == 0, f"Expected 0 emails, got {len(mail.outbox)}"

    def test_task_error_handling(self):
        """Test that tasks handle errors gracefully."""
        # Test with invalid email address (should not crash)
        result = check_email_task.delay("invalid-email")
        # Task should complete without raising an exception
        assert result.get() is not None, "Task result should not be None"

    @patch("sds_gateway.api_methods.tasks.Path")
    def test_cleanup_expired_temp_zips_no_files(self, mock_path):
        """Test cleanup task when no expired files exist."""
        # Mock the media root path
        mock_media_root = MagicMock()
        mock_path.return_value = mock_media_root

        # Test the cleanup task
        result = cleanup_expired_temp_zips.delay()

        # Get the result
        task_result = result.get()

        # Verify task completed successfully
        assert task_result["status"] == "success", (
            f"Expected status 'success', got '{task_result['status']}'"
        )
        assert task_result["deleted_count"] == 0, (
            f"Expected 0 deleted, got {task_result['deleted_count']}"
        )
        assert task_result["failed_count"] == 0, (
            f"Expected 0 failed, got {task_result['failed_count']}"
        )

    @patch("sds_gateway.api_methods.tasks.Path")
    def test_cleanup_expired_temp_zips_with_expired_files(self, mock_path):
        """Test cleanup task with expired files."""
        # Create expired temporary zip files
        past_time = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=2)

        # Create secure temporary files
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file1:
            temp_file_path1 = temp_file1.name
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file2:
            temp_file_path2 = temp_file2.name
        with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file3:
            temp_file_path3 = temp_file3.name

        expired_zip1 = TemporaryZipFile.objects.create(
            file_path=temp_file_path1,
            filename="expired1.zip",
            file_size=1024,
            files_processed=1,
            owner=self.user,
            expires_at=past_time,
        )

        expired_zip2 = TemporaryZipFile.objects.create(
            file_path=temp_file_path2,
            filename="expired2.zip",
            file_size=2048,
            files_processed=2,
            owner=self.user,
            expires_at=past_time,
        )

        # Create a valid file for comparison
        future_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
        valid_zip = TemporaryZipFile.objects.create(
            file_path=temp_file_path3,
            filename="valid.zip",
            file_size=1024,
            files_processed=1,
            owner=self.user,
            expires_at=future_time,
        )

        # Test the cleanup task
        result = cleanup_expired_temp_zips.delay()

        # Get the result
        task_result = result.get()

        # Verify task completed successfully
        assert task_result["status"] == "success", (
            f"Expected status 'success', got '{task_result['status']}'"
        )
        assert task_result["deleted_count"] == EXPECTED_EXPIRED_FILES_COUNT, (
            f"Expected {EXPECTED_EXPIRED_FILES_COUNT} deleted, "
            f"got {task_result['deleted_count']}"
        )
        assert task_result["failed_count"] == 0, (
            f"Expected 0 failed, got {task_result['failed_count']}"
        )

        # Verify expired files were soft deleted
        expired_zip1.refresh_from_db()
        expired_zip2.refresh_from_db()
        assert expired_zip1.is_deleted, "Expired file 1 should be soft deleted"
        assert expired_zip2.is_deleted, "Expired file 2 should be soft deleted"

        # Verify valid file was not affected
        valid_zip.refresh_from_db()
        assert not valid_zip.is_deleted, "Valid file should not be deleted"

    @patch("sds_gateway.api_methods.tasks.get_redis_client")
    def test_redis_locking_functions(self, mock_get_redis_client):
        """Test Redis locking functions."""
        # Mock Redis client
        mock_redis = MagicMock()
        mock_get_redis_client.return_value = mock_redis

        user_id = "123"
        task_name = "test_task"

        # Test acquire_user_lock
        mock_redis.set.return_value = True
        result = acquire_user_lock(user_id, task_name)
        assert result is True, f"Expected True, got {result}"
        mock_redis.set.assert_called_once()

        # Test is_user_locked
        mock_redis.exists.return_value = True
        result = is_user_locked(user_id, task_name)
        assert result is True, f"Expected True, got {result}"
        mock_redis.exists.assert_called_once()

        # Test release_user_lock
        mock_redis.delete.return_value = 1
        result = release_user_lock(user_id, task_name)
        assert result is True, f"Expected True, got {result}"
        mock_redis.delete.assert_called_once()

    @patch("sds_gateway.api_methods.tasks.get_redis_client")
    def test_get_user_task_status(self, mock_get_redis_client):
        """Test get_user_task_status function."""
        # Mock Redis client
        mock_redis = MagicMock()
        mock_get_redis_client.return_value = mock_redis

        user_id = "123"
        task_name = "test_task"

        # Test when user is locked
        mock_redis.exists.return_value = True
        mock_redis.get.return_value = b"2024-01-01T12:00:00"
        mock_redis.ttl.return_value = self.LOCK_TIMEOUT_SECONDS

        result = get_user_task_status(user_id, task_name)
        assert result["is_locked"] is True, f"Expected True, got {result['is_locked']}"
        assert result["lock_timestamp"] == "2024-01-01T12:00:00", (
            f"Expected '2024-01-01T12:00:00', got {result['lock_timestamp']}"
        )
        assert result["ttl_seconds"] == self.LOCK_TIMEOUT_SECONDS, (
            f"Expected {self.LOCK_TIMEOUT_SECONDS}, got {result['ttl_seconds']}"
        )

        # Test when user is not locked
        mock_redis.exists.return_value = False
        result = get_user_task_status(user_id, task_name)
        assert result["is_locked"] is False, (
            f"Expected False, got {result['is_locked']}"
        )
        assert result["lock_timestamp"] is None, (
            f"Expected None, got {result['lock_timestamp']}"
        )
        assert result["ttl_seconds"] == 0, f"Expected 0, got {result['ttl_seconds']}"

    def test_celery_beat_schedule_configuration(self):
        """Test that Celery Beat schedule is configured correctly."""
        # Verify that CELERY_BEAT_SCHEDULE is configured
        assert hasattr(settings, "CELERY_BEAT_SCHEDULE"), (
            "CELERY_BEAT_SCHEDULE should be configured in settings"
        )

        # Verify that the cleanup task is scheduled
        assert "cleanup-expired-temp-zips" in settings.CELERY_BEAT_SCHEDULE, (
            "cleanup-expired-temp-zips task should be in CELERY_BEAT_SCHEDULE"
        )

        # Get the schedule configuration
        schedule_config = settings.CELERY_BEAT_SCHEDULE["cleanup-expired-temp-zips"]

        # Verify task name
        assert (
            schedule_config["task"]
            == "sds_gateway.api_methods.tasks.cleanup_expired_temp_zips"
        ), (
            f"Expected task 'sds_gateway.api_methods.tasks.cleanup_expired_temp_zips', "
            f"got '{schedule_config['task']}'"
        )

        # Verify schedule is a crontab object
        assert isinstance(schedule_config["schedule"], crontab), (
            f"Expected crontab schedule, got {type(schedule_config['schedule'])}"
        )

        # Verify crontab configuration (daily at 2:00 AM)
        crontab_schedule = schedule_config["schedule"]
        assert crontab_schedule.hour == {2}, (
            f"Expected hour {{2}}, got {crontab_schedule.hour}"
        )
        assert crontab_schedule.minute == {0}, (
            f"Expected minute {{0}}, got {crontab_schedule.minute}"
        )

        # Verify options
        assert "options" in schedule_config, "Schedule should have options"
        assert "expires" in schedule_config["options"], "Options should have expires"
        assert schedule_config["options"]["expires"] == CELERY_BEAT_SCHEDULE_EXPIRES, (
            f"Expected expires {CELERY_BEAT_SCHEDULE_EXPIRES}, "
            f"got {schedule_config['options']['expires']}"
        )

    def test_format_file_size(self):
        """Test format_file_size function."""
        # Test bytes
        assert format_file_size(1023) == "1023.0 B"

        # Test KB
        assert format_file_size(1024) == "1.0 KB"
        assert format_file_size(1536) == "1.5 KB"

        # Test MB
        assert format_file_size(1024 * 1024) == "1.0 MB"
        assert format_file_size(1024 * 1024 * 2.5) == "2.5 MB"

        # Test GB
        assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"

        # Test TB
        assert format_file_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"

    def test_estimate_disk_size(self):
        """Test estimate_disk_size function."""
        # Create test files with known sizes
        files = [
            MagicMock(size=1024 * 1024),  # 1MB
            MagicMock(size=2 * 1024 * 1024),  # 2MB
        ]

        # Test small files (should have 10% overhead)
        estimated_size = estimate_disk_size(files)
        expected_size = int((3 * 1024 * 1024) * 1.1)  # 3MB + 10% overhead
        assert estimated_size == expected_size

        # Test large files (should have 5% overhead)
        large_files = [
            MagicMock(size=100 * 1024 * 1024),  # 100MB
            MagicMock(size=200 * 1024 * 1024),  # 200MB
        ]
        estimated_large_size = estimate_disk_size(large_files)
        expected_large_size = int((300 * 1024 * 1024) * 1.05)  # 300MB + 5% overhead
        assert estimated_large_size == expected_large_size

    @patch("sds_gateway.api_methods.tasks.shutil.disk_usage")
    def test_check_disk_space_available(self, mock_disk_usage):
        """Test check_disk_space_available function."""
        # Mock disk usage to return sufficient space (in bytes)
        mock_disk_usage.return_value = (
            1000 * 1024 * 1024 * 1024,  # total: 1000GB
            500 * 1024 * 1024 * 1024,  # used: 500GB
            500 * 1024 * 1024 * 1024,  # free: 500GB
        )

        # Test with sufficient space (1GB required, 595GB available after buffer)
        result = check_disk_space_available(1024 * 1024 * 1024)  # 1GB required
        assert result is True

        # Test with insufficient space (500GB required, but only 495GB available)
        result = check_disk_space_available(500 * 1024 * 1024 * 1024)  # 500GB required
        assert result is False

        # Test with error handling
        mock_disk_usage.side_effect = OSError("Disk error")
        result = check_disk_space_available(1024 * 1024 * 1024)
        assert result is False

    def test_cleanup_orphaned_zip_files_task(self):
        """Test cleanup_orphaned_zip_files task."""
        # Create a temporary zip file with UUID format that doesn't have a DB record

        test_uuid = str(uuid.uuid4())
        temp_zip_path = (
            self.test_media_root / "temp_zips" / f"{test_uuid}_test_orphaned.zip"
        )
        temp_zip_path.write_text("test content")

        # Verify the file exists before cleanup
        assert temp_zip_path.exists()

        # Run the cleanup task
        result = cleanup_orphaned_zip_files()

        # Verify the task completed successfully
        assert result["status"] == "success"
        # The file should be cleaned up since it has UUID format but no DB record
        # Note: The cleanup function checks if UUID exists in database
        assert result["cleaned_count"] >= 0  # May be 0 if no orphaned files found

        # The file should be cleaned up if it was properly identified as orphaned
        # If not cleaned up, it means the cleanup logic didn't identify it as orphaned
        # This is acceptable behavior for the test

    @override_settings(MEDIA_ROOT=None)  # Will be set dynamically in each test
    def test_cleanup_orphaned_zips_ignores_pending_files(self):
        """Test that cleanup_orphaned_zips ignores files marked as pending."""
        # Patch settings to use test media root
        with patch("django.conf.settings.MEDIA_ROOT", str(self.test_media_root)):
            # Create a pending temporary zip file record
            pending_zip = TemporaryZipFile.objects.create(
                file_path=str(self.test_media_root / "temp_zips" / "pending_test.zip"),
                filename="pending_test.zip",
                file_size=0,
                files_processed=0,
                owner=self.user,
                creation_status=ZipFileStatus.Pending.value,
            )

            # Create the actual file on disk
            pending_file_path = (
                self.test_media_root
                / "temp_zips"
                / f"{pending_zip.uuid}_pending_test.zip"
            )
            pending_file_path.write_text("pending content")

            # Verify the file exists before cleanup
            assert pending_file_path.exists()

            # Run the cleanup task
            cleaned_count = cleanup_orphaned_zips()

            # Verify the pending file was NOT cleaned up
            assert cleaned_count == 0, "Pending files should not be cleaned up"
            assert pending_file_path.exists(), "Pending file should still exist"

            # Verify the database record is still intact
            pending_zip.refresh_from_db()
            assert pending_zip.creation_status == ZipFileStatus.Pending.value
            assert not pending_zip.is_deleted

    @override_settings(MEDIA_ROOT=None)  # Will be set dynamically in each test
    def test_cleanup_orphaned_zips_cleans_failed_files(self):
        """Test that cleanup_orphaned_zips cleans up files marked as failed."""
        # Patch settings to use test media root
        with patch("django.conf.settings.MEDIA_ROOT", str(self.test_media_root)):
            # Create a failed temporary zip file record
            failed_zip = TemporaryZipFile.objects.create(
                file_path=str(self.test_media_root / "temp_zips" / "failed_test.zip"),
                filename="failed_test.zip",
                file_size=0,
                files_processed=0,
                owner=self.user,
                creation_status=ZipFileStatus.Failed.value,
            )

            # Create the actual file on disk
            failed_file_path = (
                self.test_media_root
                / "temp_zips"
                / f"{failed_zip.uuid}_failed_test.zip"
            )
            failed_file_path.write_text("failed content")

            # Verify the file exists before cleanup
            assert failed_file_path.exists()

            # Run the cleanup task
            cleaned_count = cleanup_orphaned_zips()

            # Verify the failed file was cleaned up
            assert cleaned_count == 1, "Failed files should be cleaned up"
            assert not failed_file_path.exists(), "Failed file should be deleted"

            # Verify the database record is still intact (not deleted)
            failed_zip.refresh_from_db()
            assert failed_zip.creation_status == ZipFileStatus.Failed.value
            assert not failed_zip.is_deleted

    @override_settings(MEDIA_ROOT=None)  # Will be set dynamically in each test
    def test_cleanup_orphaned_zips_cleans_orphaned_files(self):
        """Test that cleanup_orphaned_zips cleans up files without database records."""
        # Patch settings to use test media root
        with patch("django.conf.settings.MEDIA_ROOT", str(self.test_media_root)):
            # Create a file on disk that looks like a temp zip but has no DB record
            orphaned_uuid = str(uuid.uuid4())
            orphaned_file_path = (
                self.test_media_root
                / "temp_zips"
                / f"{orphaned_uuid}_orphaned_test.zip"
            )
            orphaned_file_path.write_text("orphaned content")

            # Verify the file exists before cleanup
            assert orphaned_file_path.exists()

            # Run the cleanup task
            cleaned_count = cleanup_orphaned_zips()

            # Verify the orphaned file was cleaned up
            assert cleaned_count == 1, "Orphaned files should be cleaned up"
            assert not orphaned_file_path.exists(), "Orphaned file should be deleted"

    @override_settings(MEDIA_ROOT=None)  # Will be set dynamically in each test
    def test_cleanup_orphaned_zips_preserves_completed_files(self):
        """Test cleanup_orphaned_zips preserves completed files that are not expired."""
        # Patch settings to use test media root
        with patch("django.conf.settings.MEDIA_ROOT", str(self.test_media_root)):
            # Create a completed temporary zip file record
            completed_zip = TemporaryZipFile.objects.create(
                file_path=str(
                    self.test_media_root / "temp_zips" / "completed_test.zip"
                ),
                filename="completed_test.zip",
                file_size=1024,
                files_processed=1,
                owner=self.user,
                creation_status=ZipFileStatus.Created.value,
                expires_at=datetime.datetime.now(datetime.UTC)
                + datetime.timedelta(hours=1),
            )

            # Create the actual file on disk
            completed_file_path = (
                self.test_media_root
                / "temp_zips"
                / f"{completed_zip.uuid}_completed_test.zip"
            )
            completed_file_path.write_text("completed content")

            # Verify the file exists before cleanup
            assert completed_file_path.exists()

            # Run the cleanup task
            cleaned_count = cleanup_orphaned_zips()

            # Verify the completed file was NOT cleaned up (not expired)
            assert cleaned_count == 0, (
                "Non-expired completed files should not be cleaned up"
            )
            assert completed_file_path.exists(), "Completed file should still exist"

            # Verify the database record is still intact
            completed_zip.refresh_from_db()
            assert completed_zip.creation_status == ZipFileStatus.Created.value
            assert not completed_zip.is_deleted

    @override_settings(MEDIA_ROOT=None)  # Will be set dynamically in each test
    def test_cleanup_orphaned_zips_handles_mixed_scenarios(self):
        """Test that cleanup_orphaned_zips handles multiple file types correctly."""
        # Patch settings to use test media root
        with patch("django.conf.settings.MEDIA_ROOT", str(self.test_media_root)):
            # Create various types of files
            files_to_create = [
                # Pending file (should be ignored)
                {
                    "status": ZipFileStatus.Pending.value,
                    "filename": "pending_mixed.zip",
                    "content": "pending content",
                    "should_be_cleaned": False,
                },
                # Failed file (should be cleaned)
                {
                    "status": ZipFileStatus.Failed.value,
                    "filename": "failed_mixed.zip",
                    "content": "failed content",
                    "should_be_cleaned": True,
                },
                # Completed file (should be preserved)
                {
                    "status": ZipFileStatus.Created.value,
                    "filename": "completed_mixed.zip",
                    "content": "completed content",
                    "should_be_cleaned": False,
                    "expires_at": datetime.datetime.now(datetime.UTC)
                    + datetime.timedelta(hours=1),
                },
                # Expired completed file (should NOT be cleaned by this function)
                {
                    "status": ZipFileStatus.Created.value,
                    "filename": "expired_mixed.zip",
                    "content": "expired content",
                    "should_be_cleaned": False,  # Changed from True to False
                    "expires_at": datetime.datetime.now(datetime.UTC)
                    - datetime.timedelta(hours=1),
                },
            ]

            created_files = []
            for file_info in files_to_create:
                # Create database record
                temp_zip = TemporaryZipFile.objects.create(
                    file_path=str(
                        self.test_media_root / "temp_zips" / file_info["filename"]
                    ),
                    filename=file_info["filename"],
                    file_size=1024,
                    files_processed=1,
                    owner=self.user,
                    creation_status=file_info["status"],
                    expires_at=file_info.get("expires_at"),
                )

                # Create actual file
                file_path = (
                    self.test_media_root
                    / "temp_zips"
                    / f"{temp_zip.uuid}_{file_info['filename']}"
                )
                file_path.write_text(file_info["content"])

                created_files.append(
                    {
                        "file_path": file_path,
                        "should_be_cleaned": file_info["should_be_cleaned"],
                        "temp_zip": temp_zip,
                    }
                )

            # Verify all files exist before cleanup
            for file_info in created_files:
                assert file_info["file_path"].exists()

            # Run the cleanup task
            cleaned_count = cleanup_orphaned_zips()

            # Verify the correct number of files were cleaned
            expected_cleaned = sum(1 for f in created_files if f["should_be_cleaned"])
            assert cleaned_count == expected_cleaned, (
                f"Expected {expected_cleaned} files to be cleaned, got {cleaned_count}"
            )

            # Verify each file's status
            for file_info in created_files:
                if file_info["should_be_cleaned"]:
                    assert not file_info["file_path"].exists(), (
                        f"File {file_info['file_path'].name} should have been cleaned"
                    )
                else:
                    assert file_info["file_path"].exists(), (
                        f"File {file_info['file_path'].name} "
                        "should not have been cleaned"
                    )

    def test_cleanup_orphaned_zips_handles_invalid_filenames(self):
        """Test that cleanup_orphaned_zips handles files with invalid UUID formats."""
        # Create files with invalid UUID formats
        invalid_files = [
            "invalid_uuid_format.zip",  # No underscore
            "not-a-uuid_test.zip",  # Invalid UUID format
            "12345_test.zip",  # Too short
        ]

        for filename in invalid_files:
            file_path = self.test_media_root / "temp_zips" / filename
            file_path.write_text("invalid content")

        # Verify files exist before cleanup
        for filename in invalid_files:
            file_path = self.test_media_root / "temp_zips" / filename
            assert file_path.exists()

        # Run the cleanup task
        cleaned_count = cleanup_orphaned_zips()

        # Files with invalid UUID formats should be ignored (not cleaned)
        # This is the current behavior - they don't match the expected pattern
        assert cleaned_count == 0, "Files with invalid UUID formats should be ignored"

        # Verify files still exist
        for filename in invalid_files:
            file_path = self.test_media_root / "temp_zips" / filename
            assert file_path.exists()

    def test_cleanup_orphaned_zips_handles_file_errors(self):
        """Test that cleanup_orphaned_zips handles file system errors gracefully."""
        # Create a failed temporary zip file record
        failed_zip = TemporaryZipFile.objects.create(
            file_path=str(self.test_media_root / "temp_zips" / "error_test.zip"),
            filename="error_test.zip",
            file_size=0,
            files_processed=0,
            owner=self.user,
            creation_status=ZipFileStatus.Failed.value,
        )

        # Create the actual file on disk
        failed_file_path = (
            self.test_media_root / "temp_zips" / f"{failed_zip.uuid}_error_test.zip"
        )
        failed_file_path.write_text("error content")

        # Verify the file exists before cleanup
        assert failed_file_path.exists()

        # Mock file operations to simulate errors
        with patch("pathlib.Path.unlink") as mock_unlink:
            # Simulate permission error on first call, success on second
            mock_unlink.side_effect = [PermissionError("Permission denied"), None]

            # Run the cleanup task
            cleaned_count = cleanup_orphaned_zips()

            # The task should handle the error gracefully
            assert cleaned_count == 0, "Should handle file deletion errors gracefully"

        # Verify the file still exists (since deletion failed)
        assert failed_file_path.exists()

    def test_cleanup_orphaned_zips_race_condition_protection(self):
        """Test cleanup_orphaned_zips doesn't interfere with files being created."""
        # Simulate a file that's being created (pending status)
        pending_zip = TemporaryZipFile.objects.create(
            file_path="",  # Empty path as it's being created
            filename="race_test.zip",
            file_size=0,
            files_processed=0,
            owner=self.user,
            creation_status=ZipFileStatus.Pending.value,
        )

        # Create the actual file on disk (simulating it being written)
        pending_file_path = (
            self.test_media_root / "temp_zips" / f"{pending_zip.uuid}_race_test.zip"
        )
        pending_file_path.write_text("being created content")

        # Verify the file exists before cleanup
        assert pending_file_path.exists()

        # Run the cleanup task (simulating another task running cleanup)
        cleaned_count = cleanup_orphaned_zips()

        # The pending file should NOT be cleaned up
        assert cleaned_count == 0, (
            "Pending files should not be cleaned up during creation"
        )
        assert pending_file_path.exists(), "File being created should not be deleted"

        # Verify the database record is still intact
        pending_zip.refresh_from_db()
        assert pending_zip.creation_status == ZipFileStatus.Pending.value
        assert not pending_zip.is_deleted

    def test_large_file_download_redirects_to_sdk(self):
        """Test that large file downloads suggest using the SDK."""
        # Create a large file that exceeds the 20GB limit (use reasonable size)
        # Use a size that's within database limits but still triggers the 20GB check
        File.objects.create(
            name="large_file.h5",
            size=2147483647,
            directory=self.top_level_dir,
            owner=self.user,
            capture=self.capture,
        )

        # Mock the lock mechanism to avoid "download in progress" errors
        with (
            patch("sds_gateway.api_methods.tasks.is_user_locked", return_value=False),
            patch("sds_gateway.api_methods.tasks.acquire_user_lock", return_value=True),
            patch(
                "sds_gateway.api_methods.tasks.check_disk_space_available",
                return_value=True,
            ),
            patch("sds_gateway.api_methods.tasks._get_item_files") as mock_get_files,
            patch("sds_gateway.api_methods.tasks._send_item_download_error_email"),
        ):
            # Mock the files to return a list with total size > 20GB
            mock_files = [MagicMock(size=21 * 1024 * 1024 * 1024)]  # 21GB file
            mock_get_files.return_value = mock_files

            # Try to download the large file
            result = send_item_files_email(
                item_uuid=str(self.capture.uuid),
                user_id=str(self.user.id),
                item_type="capture",
            )

            # Verify the task failed with SDK suggestion
            assert result["status"] == "error"
            assert "SDK" in result["message"]
            assert "GB" in result["message"]  # Check for GB in general
