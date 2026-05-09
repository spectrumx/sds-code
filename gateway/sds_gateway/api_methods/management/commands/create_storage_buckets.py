"""Management command to create/ensure buckets exist on configured object stores."""

from django.conf import settings
from django.core.management.base import BaseCommand
from loguru import logger as log

from sds_gateway.api_methods.utils.minio_client import _build_minio_client


class Command(BaseCommand):
    """Create or ensure buckets exist on primary and optional secondary stores."""

    help = "Create/ensure buckets exist on configured object stores"

    def handle(self, *args, **options) -> None:
        """Execute the command."""
        # Primary store (required)
        primary_client = _build_minio_client(
            endpoint=settings.PRIMARY_ENDPOINT_URL,
            access_key=settings.PRIMARY_ACCESS_KEY_ID,
            secret_key=settings.PRIMARY_SECRET_ACCESS_KEY,
            secure=settings.PRIMARY_STORAGE_USE_HTTPS,
        )
        self._ensure_bucket(primary_client, settings.PRIMARY_STORAGE_BUCKET_NAME)

        # Secondary store (optional — may be unreachable)
        # Skip entirely if access key is still the LEGACY fallback default;
        # that means no secondary was ever configured for this environment.
        if settings.SECONDARY_ACCESS_KEY_ID == settings.LEGACY_AWS_ACCESS_KEY_ID:
            log.info(
                "Secondary object store not configured (LEGACY fallback creds), "
                "skipping"
            )
        else:
            try:
                secondary_client = _build_minio_client(
                    endpoint=settings.SECONDARY_ENDPOINT_URL,
                    access_key=settings.SECONDARY_ACCESS_KEY_ID,
                    secret_key=settings.SECONDARY_SECRET_ACCESS_KEY,
                    secure=settings.SECONDARY_STORAGE_USE_HTTPS,
                )
                self._ensure_bucket(
                    secondary_client, settings.SECONDARY_STORAGE_BUCKET_NAME
                )
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "Secondary object store unreachable or bucket creation failed: {}",
                    exc,
                )

    def _ensure_bucket(self, client, bucket_name: str) -> None:
        """Check if a bucket exists; create it if it does not."""
        if client.bucket_exists(bucket_name):
            log.info("Bucket '{}' already exists", bucket_name)
            return

        client.make_bucket(bucket_name)
        log.success("Created bucket '{}'", bucket_name)
