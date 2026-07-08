"""Mark a dataset and its captures as public + FINAL for federation export."""

from __future__ import annotations

from uuid import UUID

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.db import transaction
from loguru import logger as log

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus


class Command(BaseCommand):
    help = (
        "Set dataset status to FINAL and is_public=True, and mark linked captures "
        "public (triggers federation Redis events when FEDERATION_ENABLED)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dataset-uuid",
            required=True,
            help="Dataset UUID to publish for federation",
        )
        parser.add_argument(
            "--capture-uuids",
            nargs="*",
            default=None,
            help="Optional capture UUIDs to attach before publishing",
        )

    def handle(self, *args, **options) -> None:
        dataset_uuid = UUID(str(options["dataset_uuid"]))
        capture_uuids = options["capture_uuids"] or []

        with transaction.atomic():
            dataset = Dataset.objects.select_for_update().get(uuid=dataset_uuid)
            if capture_uuids:
                captures = Capture.objects.filter(
                    uuid__in=[UUID(str(u)) for u in capture_uuids],
                    is_deleted=False,
                )
                missing = set(capture_uuids) - {
                    str(c.uuid) for c in captures
                }
                if missing:
                    msg = f"Captures not found: {sorted(missing)}"
                    raise CommandError(msg)
                dataset.captures.add(*captures)

            Capture.objects.filter(
                datasets=dataset,
                is_deleted=False,
            ).update(is_public=True)

            dataset.status = DatasetStatus.FINAL
            dataset.is_public = True
            dataset.save(update_fields=["status", "is_public", "updated_at"])

        log.info(
            "Published dataset {} for federation export (FINAL, public)",
            dataset_uuid,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Dataset {dataset_uuid} is FINAL and public. "
                "Re-run federation bootstrap or save again to re-index if needed.",
            ),
        )
