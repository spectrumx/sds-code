"""
Tests for Celery tasks in the API methods app.
"""

import datetime
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch

from celery.exceptions import SoftTimeLimitExceeded
from celery.schedules import crontab
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase
from django.test import override_settings

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import TemporaryZipFile
from sds_gateway.api_methods.tasks import acquire_user_lock
from sds_gateway.api_methods.tasks import check_celery_task
from sds_gateway.api_methods.tasks import check_email_task
from sds_gateway.api_methods.tasks import cleanup_expired_temp_zips
from sds_gateway.api_methods.tasks import get_user_task_status
from sds_gateway.api_methods.tasks import is_user_locked
from sds_gateway.api_methods.tasks import release_user_lock
from sds_gateway.api_methods.tasks import send_item_files_email

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

        self.base_dir = "/files/test@example.com/"
        self.rel_path_capture = "captures/test_capture/"
        self.rel_path_artifacts = "artifacts/"
        self.top_level_dir = f"{self.base_dir}{self.rel_path_capture}"

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

        # Create test files
        self.file1 = File.objects.create(
            name="test_file1.txt",
            size=1024,
            directory=self.top_level_dir,
            owner=self.user,
            capture=self.capture,
        )

        self.file2 = File.objects.create(
            name="test_file2.txt",
            size=2048,
            directory=f"{self.top_level_dir}subdir/",
            owner=self.user,
            capture=self.capture,
        )

        self.file3 = File.objects.create(
            name="test_file3.txt",
            size=3072,
            directory=f"{self.base_dir}{self.rel_path_artifacts}",
            owner=self.user,
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

    @patch("sds_gateway.api_methods.utils.minio_client.get_minio_client")
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
        # Mock MinIO client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.stream.return_value = [b"test file content"]
        mock_response.close.return_value = None
        mock_response.release_conn.return_value = None
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

    @patch("sds_gateway.api_methods.tasks.acquire_user_lock")
    @patch("sds_gateway.api_methods.tasks.release_user_lock")
    @patch("sds_gateway.api_methods.tasks.is_user_locked")
    def test_send_dataset_files_email_download_failure(
        self, mock_is_locked, mock_release_lock, mock_acquire_lock
    ):
        """Test dataset email task when file download fails."""
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
