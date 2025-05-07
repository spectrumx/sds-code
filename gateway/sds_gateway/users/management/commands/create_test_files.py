import secrets
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import DatabaseError
from django.db import IntegrityError
from django.db import transaction
from django.utils import timezone

from sds_gateway.captures.models import Capture
from sds_gateway.files.models import File
from sds_gateway.minio_client import MinioClient

User = get_user_model()  # This is the only User import we need


class Command(BaseCommand):
    help = "Create test files and captures for development"

    def handle(self, *args, **options):
        try:
            if not settings.DEBUG:
                self.stdout.write(
                    self.style.ERROR(
                        "This command can only be run in local development environment"
                    )
                )
                return
            user = self._get_or_create_test_user()
            self._create_test_files(user)
            self._create_test_captures(user)
        except (DatabaseError, IntegrityError) as e:
            self.stdout.write(self.style.ERROR(f"Database error: {e}"))
        except OSError as e:
            self.stdout.write(self.style.ERROR(f"I/O error: {e}"))

    def _get_or_create_test_user(self):
        """Get or create a test user."""
        try:
            return User.objects.get_or_create(
                email="test@example.com",
                defaults={
                    "name": "Test User",
                    "is_staff": True,
                    "is_superuser": True,
                },
            )[0]
        except DatabaseError as e:
            self.stdout.write(self.style.ERROR(f"Failed to create test user: {e}"))
            raise

    def _create_test_files(self, user):
        """Create test files in MinIO."""
        # Define test directories and file types
        directories = [Path(f"files/{user.email}/test_dir_{i}") for i in range(3)]

        file_types = [
            ("txt", b"Test content"),
            ("csv", b"id,name\n1,test"),
            ("json", b'{"test": "data"}'),
        ]

        # Create directories if they don't exist
        for directory in directories:
            directory_path = Path(str(directory))
            directory_path.mkdir(parents=True, exist_ok=True)

        # Create files
        minio_client = MinioClient()
        created_files = []

        try:
            for directory in directories:
                for i in range(3):
                    file_type, content = secrets.choice(file_types)
                    file_name = f"test_file_{i}.{file_type}"
                    file_path = directory / file_name

                    # Save file
                    with file_path.open("wb") as f:
                        f.write(content)

                    # Upload to MinIO
                    minio_client.upload_file(
                        str(file_path),
                        str(file_path),
                        f"text/{file_type}",
                    )

                    # Create file record
                    file_obj = File.objects.create(
                        name=file_name,
                        directory=str(directory),
                        media_type=f"text/{file_type}",
                        size=len(content),
                        owner=user,
                    )
                    created_files.append(file_obj)

                    self.stdout.write(self.style.SUCCESS(f"Created file: {file_path}"))
        except (OSError, DatabaseError) as e:
            self.stdout.write(self.style.ERROR(f"Failed to create test files: {e}"))
            raise
        else:
            return created_files

    def _create_test_captures(self, user):
        """Create test captures."""
        capture_types = ["rh", "drf"]
        channels = ["ch1", "ch2", "ch3"]
        scan_groups = ["group1", "group2"]

        try:
            with transaction.atomic():
                for i in range(5):
                    capture_type = secrets.choice(capture_types)
                    channel = secrets.choice(channels)
                    scan_group = secrets.choice(scan_groups)
                    top_level_dir = f"captures/{user.email}/test_capture_{i}"

                    capture = Capture.objects.create(
                        capture_type=capture_type,
                        top_level_dir=top_level_dir,
                        channel=channel,
                        scan_group=scan_group,
                        owner=user,
                        created_at=timezone.now() - timedelta(days=i),
                    )

                    # Associate some random files with the capture
                    associated_files = File.objects.filter(owner=user).order_by("?")[:3]
                    capture.files.set(associated_files)

                    self.stdout.write(self.style.SUCCESS(f"Created capture: {capture}"))

        except (DatabaseError, IntegrityError) as e:
            self.stdout.write(self.style.WARNING(f"Failed to create capture {i}: {e}"))
