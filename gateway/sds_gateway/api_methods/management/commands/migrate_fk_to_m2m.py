"""Management command to migrate ForeignKey relationships to ManyToMany relationships.

This command migrates:
- File.dataset FK → File.datasets M2M
- File.capture FK → File.captures M2M
- Capture.dataset FK → Capture.datasets M2M
"""

from django.core.management.base import BaseCommand
from loguru import logger

from sds_gateway.api_methods.models import Capture, File


class Command(BaseCommand):
    help = "Migrate ForeignKey relationships to ManyToMany relationships"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of records to process in each batch (default: 1000)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be migrated without actually migrating",
        )

    def handle(self, *args, **options):
        batch_size = options["batch_size"]
        dry_run = options["dry_run"]

        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No changes will be made"))

        # Migrate File.dataset FK → File.datasets M2M
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Migrating File.dataset → File.datasets")
        self.stdout.write("=" * 60)
        self._migrate_file_datasets(batch_size, dry_run)

        # Migrate File.capture FK → File.captures M2M
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Migrating File.capture → File.captures")
        self.stdout.write("=" * 60)
        self._migrate_file_captures(batch_size, dry_run)

        # Migrate Capture.dataset FK → Capture.datasets M2M
        self.stdout.write("\n" + "=" * 60)
        self.stdout.write("Migrating Capture.dataset → Capture.datasets")
        self.stdout.write("=" * 60)
        self._migrate_capture_datasets(batch_size, dry_run)

        self.stdout.write("\n" + self.style.SUCCESS("Migration complete!"))

    def _migrate_file_datasets(self, batch_size, dry_run):
        """Migrate File.dataset ForeignKey to File.datasets ManyToMany."""
        files_with_dataset = File.objects.filter(
            dataset__isnull=False
        ).select_related("dataset")

        total_count = files_with_dataset.count()
        if total_count == 0:
            self.stdout.write("No files with dataset FK found.")
            return

        self.stdout.write(f"Found {total_count} files with dataset FK")
        if dry_run:
            self.stdout.write(f"Would migrate {total_count} file-dataset relationships")
            return

        migrated_count = 0
        skipped_count = 0

        # Process in batches
        for offset in range(0, total_count, batch_size):
            batch = files_with_dataset[offset : offset + batch_size]
            batch_end = min(offset + batch_size, total_count)

            for file in batch:
                if file.dataset:
                    # Check if relationship already exists (idempotent)
                    if file.datasets.filter(uuid=file.dataset.uuid).exists():
                        skipped_count += 1
                        continue

                    file.datasets.add(file.dataset)
                    migrated_count += 1

            self.stdout.write(
                f"Processed {batch_end}/{total_count} files "
                f"({migrated_count} migrated, {skipped_count} skipped)"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"File.datasets migration complete: "
                f"{migrated_count} migrated, {skipped_count} already existed"
            )
        )

    def _migrate_file_captures(self, batch_size, dry_run):
        """Migrate File.capture ForeignKey to File.captures ManyToMany."""
        files_with_capture = File.objects.filter(
            capture__isnull=False
        ).select_related("capture")

        total_count = files_with_capture.count()
        if total_count == 0:
            self.stdout.write("No files with capture FK found.")
            return

        self.stdout.write(f"Found {total_count} files with capture FK")
        if dry_run:
            self.stdout.write(f"Would migrate {total_count} file-capture relationships")
            return

        migrated_count = 0
        skipped_count = 0

        # Process in batches
        for offset in range(0, total_count, batch_size):
            batch = files_with_capture[offset : offset + batch_size]
            batch_end = min(offset + batch_size, total_count)

            for file in batch:
                if file.capture:
                    # Check if relationship already exists (idempotent)
                    if file.captures.filter(uuid=file.capture.uuid).exists():
                        skipped_count += 1
                        continue

                    file.captures.add(file.capture)
                    migrated_count += 1

            self.stdout.write(
                f"Processed {batch_end}/{total_count} files "
                f"({migrated_count} migrated, {skipped_count} skipped)"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"File.captures migration complete: "
                f"{migrated_count} migrated, {skipped_count} already existed"
            )
        )

    def _migrate_capture_datasets(self, batch_size, dry_run):
        """Migrate Capture.dataset ForeignKey to Capture.datasets ManyToMany."""
        captures_with_dataset = Capture.objects.filter(
            dataset__isnull=False
        ).select_related("dataset")

        total_count = captures_with_dataset.count()
        if total_count == 0:
            self.stdout.write("No captures with dataset FK found.")
            return

        self.stdout.write(f"Found {total_count} captures with dataset FK")
        if dry_run:
            self.stdout.write(f"Would migrate {total_count} capture-dataset relationships")
            return

        migrated_count = 0
        skipped_count = 0

        # Process in batches
        for offset in range(0, total_count, batch_size):
            batch = captures_with_dataset[offset : offset + batch_size]
            batch_end = min(offset + batch_size, total_count)

            for capture in batch:
                if capture.dataset:
                    # Check if relationship already exists (idempotent)
                    if capture.datasets.filter(uuid=capture.dataset.uuid).exists():
                        skipped_count += 1
                        continue

                    capture.datasets.add(capture.dataset)
                    migrated_count += 1

            self.stdout.write(
                f"Processed {batch_end}/{total_count} captures "
                f"({migrated_count} migrated, {skipped_count} skipped)"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Capture.datasets migration complete: "
                f"{migrated_count} migrated, {skipped_count} already existed"
            )
        )

