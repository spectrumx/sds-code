"""
Management command to test Celery tasks.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from loguru import logger

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.tasks import send_dataset_files_email
from sds_gateway.api_methods.tasks import test_celery_task
from sds_gateway.api_methods.tasks import test_email_task

User = get_user_model()


class Command(BaseCommand):
    """Command to test Celery tasks."""

    help = "Test Celery tasks functionality"

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--email",
            type=str,
            default="test@example.com",
            help="Email address for testing email tasks",
        )
        parser.add_argument(
            "--dataset-uuid",
            type=str,
            help="Dataset UUID for testing dataset download task",
        )
        parser.add_argument(
            "--task",
            type=str,
            choices=["basic", "email", "dataset", "all"],
            default="all",
            help="Which task(s) to test",
        )

    def handle(self, *args, **options):
        """Handle the command."""
        email = options["email"]
        dataset_uuid = options["dataset_uuid"]
        task_type = options["task"]

        logger.info("🚀 Starting Celery task tests...")

        if task_type in ["basic", "all"]:
            self.test_basic_task()

        if task_type in ["email", "all"]:
            self.test_email_task(email)

        if task_type in ["dataset", "all"]:
            self.test_dataset_task(dataset_uuid)

        logger.success("✅ Celery task tests completed!")

    def test_basic_task(self):
        """Test the basic Celery task."""
        logger.info("📝 Testing basic Celery task...")

        try:
            result = test_celery_task.delay("Test from management command")
            task_result = result.get(timeout=10)

            logger.success(f"✅ Basic task result: {task_result}")
        except (OSError, ValueError, TimeoutError) as e:
            logger.error(f"❌ Basic task failed: {e}")

    def test_email_task(self, email):
        """Test the email task."""
        logger.info(f"📧 Testing email task to {email}...")

        try:
            result = test_email_task.delay(email)
            task_result = result.get(timeout=10)

            logger.success(f"✅ Email task result: {task_result}")
            logger.warning("📬 Check MailHog at http://localhost:8025 to see the email")
        except (OSError, ValueError, TimeoutError) as e:
            logger.error(f"❌ Email task failed: {e}")

    def test_dataset_task(self, dataset_uuid):
        """Test the dataset download task."""
        if not dataset_uuid:
            # Try to find a dataset automatically
            try:
                dataset = Dataset.objects.filter(is_deleted=False).first()
                if dataset:
                    dataset_uuid = str(dataset.uuid)
                    logger.info(f"🔍 Using dataset: {dataset.name} ({dataset_uuid})")
                else:
                    logger.warning("⚠️  No datasets found. Skipping dataset task test.")
                    return
            except (OSError, ValueError) as e:
                logger.error(f"❌ Error finding dataset: {e}")
                return

        logger.info(f"📦 Testing dataset download task for {dataset_uuid}...")

        try:
            result = send_dataset_files_email.delay(dataset_uuid, "test@example.com")
            task_result = result.get(timeout=30)  # Longer timeout for file processing

            logger.success(f"✅ Dataset task result: {task_result}")

            if task_result.get("status") == "success":
                logger.warning(
                    "📬 Check MailHog at http://localhost:8025 to see the dataset email"
                )
        except (OSError, ValueError, TimeoutError) as e:
            logger.error(f"❌ Dataset task failed: {e}")
