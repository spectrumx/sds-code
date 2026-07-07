"""Convert dataset authors from old string format to new object format.

Old format: ["Author One", "Author Two"]                    (list of strings)
New format: [{"name": "Author One", "orcid_id": ""}, ...]   (list of dicts)

This is a one-time data fix for datasets that were created or versioned
before the model-level auto-normalization was added to Dataset.save().
"""

from django.core.management.base import BaseCommand
from loguru import logger

from sds_gateway.api_methods.models import Dataset


class Command(BaseCommand):
    help = (
        "Convert dataset authors from old string format ['Name'] "
        "to new object format [{'name': 'Name', 'orcid_id': ''}]"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Only count affected datasets without modifying them",
        )
        parser.add_argument(
            "--uuid",
            type=str,
            help="Migrate only a specific dataset by UUID",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        specific_uuid = options.get("uuid")

        # Query datasets with non-empty authors
        queryset = Dataset.objects.filter(authors__isnull=False).exclude(authors="")
        if specific_uuid:
            queryset = queryset.filter(uuid=specific_uuid)

        total = queryset.count()
        updated = 0
        skipped = 0
        errors = 0

        self.stdout.write(f"Scanning {total} dataset(s) with authors...")

        for dataset in queryset:
            try:
                # from_db already deserialized authors from JSON string to Python object
                authors = dataset.authors

                # Skip if not a list
                if not isinstance(authors, list):
                    skipped += 1
                    continue

                # Skip empty lists
                if not authors:
                    skipped += 1
                    continue

                # Skip if already in new format (list of dicts with 'name' key)
                if isinstance(authors[0], dict):
                    skipped += 1
                    continue

                # Convert old format: list of strings → list of dicts
                if isinstance(authors[0], str):
                    new_authors = [
                        {"name": author, "orcid_id": ""}
                        for author in authors
                        if isinstance(author, str)
                    ]

                    if not new_authors:
                        logger.warning(
                            f"Dataset {dataset.uuid}: no valid author strings found, "
                            "skipping",
                        )
                        skipped += 1
                        continue

                    if dry_run:
                        logger.info(
                            f"[DRY-RUN] Would convert dataset {dataset.uuid}: "
                            f"{len(authors)} author(s) in old format"
                        )
                    else:
                        dataset.authors = new_authors
                        dataset.save(update_fields=["authors"])
                        logger.info(
                            f"Converted dataset {dataset.uuid}: "
                            f"{len(authors)} author(s) → new format"
                        )
                    updated += 1
                else:
                    # Unexpected format
                    logger.warning(
                        f"Dataset {dataset.uuid}: unexpected author type "
                        f"{type(authors[0]).__name__}, skipping"
                    )
                    skipped += 1

            except Exception as e:  # noqa: BLE001  # intentional: continue processing remaining datasets
                logger.error(f"Error processing dataset {dataset.uuid}: {e}")
                errors += 1

        self.stdout.write(
            f"Done: {updated} updated, {skipped} skipped, {errors} errors"
            + (" (dry run)" if dry_run else "")
        )
