"""Management command to update dataset authors from string format to object format."""

import json
import logging
from typing import Any

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction

from sds_gateway.api_methods.models import Dataset

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """Update dataset authors from string format to object format."""

    help = (
        "Update dataset authors from string format to object format. "
        "Converts authors from ['Author1', 'Author2'] to "
        "[{'name': 'Author1', 'orcid_id': ''}, {'name': 'Author2', 'orcid_id': ''}]"
    )

    def add_arguments(self, parser):
        """Add command arguments."""
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be updated without making changes",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="Number of datasets to process in each batch (default: 100)",
        )
        parser.add_argument(
            "--dataset-ids",
            nargs="*",
            type=str,
            help="Specific dataset UUIDs to update (if not provided, all datasets are processed)",
        )

    def handle(self, *args, **options):
        """Handle the command execution."""
        dry_run = options["dry_run"]
        batch_size = options["batch_size"]
        dataset_ids = options["dataset_ids"]

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting dataset authors update{' (DRY RUN)' if dry_run else ''}..."
            )
        )

        # Get datasets to update
        if dataset_ids:
            datasets = Dataset.objects.filter(uuid__in=dataset_ids)
            if not datasets.exists():
                raise CommandError(f"No datasets found with the provided UUIDs: {dataset_ids}")
        else:
            datasets = Dataset.objects.all()

        total_datasets = datasets.count()
        self.stdout.write(f"Found {total_datasets} datasets to process")

        if total_datasets == 0:
            self.stdout.write(self.style.WARNING("No datasets found to update"))
            return

        updated_count = 0
        skipped_count = 0
        error_count = 0

        # Process datasets in batches
        for i in range(0, total_datasets, batch_size):
            batch = datasets[i : i + batch_size]
            self.stdout.write(f"Processing batch {i//batch_size + 1} ({len(batch)} datasets)")

            for dataset in batch:
                try:
                    result = self._update_dataset_authors(dataset, dry_run)
                    if result == "updated":
                        updated_count += 1
                    elif result == "skipped":
                        skipped_count += 1
                except Exception as e:
                    error_count += 1
                    logger.error(f"Error updating dataset {dataset.uuid}: {e}")
                    self.stdout.write(
                        self.style.ERROR(f"Error updating dataset {dataset.uuid}: {e}")
                    )

        # Summary
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write("SUMMARY:")
        self.stdout.write(f"Total datasets processed: {total_datasets}")
        self.stdout.write(self.style.SUCCESS(f"Updated: {updated_count}"))
        self.stdout.write(self.style.WARNING(f"Skipped: {skipped_count}"))
        if error_count > 0:
            self.stdout.write(self.style.ERROR(f"Errors: {error_count}"))

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    "\nThis was a dry run. No changes were made. "
                    "Run without --dry-run to apply changes."
                )
            )

    def _update_dataset_authors(self, dataset: Dataset, dry_run: bool) -> str:
        """Update a single dataset's authors field."""
        if not dataset.authors:
            self.stdout.write(f"  Dataset {dataset.uuid}: No authors to update")
            return "skipped"

        # Parse current authors
        try:
            if isinstance(dataset.authors, str):
                current_authors = json.loads(dataset.authors)
            else:
                current_authors = dataset.authors
        except (json.JSONDecodeError, TypeError):
            self.stdout.write(
                f"  Dataset {dataset.uuid}: Invalid authors format, skipping"
            )
            return "skipped"

        if not current_authors:
            self.stdout.write(f"  Dataset {dataset.uuid}: Empty authors list")
            return "skipped"

        # Check if already in new format
        if isinstance(current_authors[0], dict) and "name" in current_authors[0]:
            self.stdout.write(f"  Dataset {dataset.uuid}: Already in new format")
            return "skipped"

        # Convert to new format
        new_authors = []
        for author in current_authors:
            if isinstance(author, str):
                new_authors.append({"name": author, "orcid_id": ""})
            else:
                # Handle unexpected format
                self.stdout.write(
                    f"  Dataset {dataset.uuid}: Unexpected author format: {author}"
                )
                new_authors.append({"name": str(author), "orcid_id": ""})

        # Show what will be updated
        self.stdout.write(f"  Dataset {dataset.uuid} ({dataset.name}):")
        self.stdout.write(f"    Old: {current_authors}")
        self.stdout.write(f"    New: {new_authors}")

        if not dry_run:
            # Update the dataset
            with transaction.atomic():
                dataset.authors = new_authors
                dataset.save(update_fields=["authors"])

        return "updated"
