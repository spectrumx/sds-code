"""Management command to clean up expired temporary zip files."""

import datetime

from django.core.management.base import BaseCommand
from loguru import logger

from sds_gateway.api_methods.models import TemporaryZipFile


class Command(BaseCommand):
    help = "Clean up expired temporary zip files"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be deleted without actually deleting",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete all temporary zip files regardless of expiration",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        force = options["force"]

        if force:
            self.stdout.write("Force mode: will delete ALL temporary zip files")
            expired_files = TemporaryZipFile.objects.all()
        else:
            self.stdout.write("Dry run mode: will only show what would be deleted")
            expired_files = TemporaryZipFile.objects.filter(
                expires_at__lt=datetime.datetime.now(datetime.UTC)
            )

        if not expired_files.exists():
            self.stdout.write("No expired files found.")
            return

        if not force:
            self.stdout.write("Files that would be deleted:")
            for temp_zip in expired_files:
                self.stdout.write(
                    f"  Would delete: {temp_zip.filename} "
                    f"(expires: {temp_zip.expires_at})"
                )
            return

        count = expired_files.count()

        self.stdout.write(f"Cleaning up {count} expired temporary zip files...")

        if dry_run:
            self.stdout.write("DRY RUN - No files will be deleted")
            for temp_zip in expired_files:
                self.stdout.write(
                    f"  Would delete: {temp_zip.filename} "
                    f"(expires: {temp_zip.expires_at})"
                )
            return

        deleted_count = 0
        failed_count = 0

        for temp_zip in expired_files:
            try:
                # Delete the file from disk
                temp_zip.delete_file()

                # Soft delete the database record and mark as expired
                temp_zip.soft_delete()
                deleted_count += 1
                self.stdout.write(f"Soft deleted: {temp_zip.filename}")
            except (OSError, ValueError) as e:
                failed_count += 1
                logger.exception(f"Failed to delete {temp_zip.filename}: {e}")
                self.stdout.write(
                    self.style.ERROR(f"Failed to delete {temp_zip.filename}: {e}")
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Cleanup complete: {deleted_count} deleted, {failed_count} failed"
            )
        )
