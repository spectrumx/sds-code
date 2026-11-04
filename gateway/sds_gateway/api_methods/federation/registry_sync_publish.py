"""Publish registry manifest via federation sync internal API."""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_manifest_build import (
    build_sync_publish_site_entries,
)
from sds_gateway.api_methods.federation.registry_manifest_publish import PublishResult
from sds_gateway.api_methods.federation.sync_client import FederationSyncClient
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


def _min_serial_for_sync_publish() -> int | None:
    value = (
        RegistryApplication.objects.filter(published_manifest_serial__isnull=False)
        .aggregate(max_serial=Max("published_manifest_serial"))
        .get("max_serial")
    )
    if value is None:
        return None
    return int(value) + 1


def _mark_applications_published(serial: int, now) -> int:
    pending = list(
        RegistryApplication.objects.filter(
            status=RegistryApplicationStatus.APPROVED.value,
        ).exclude(site_name="")
    )
    if not pending:
        return 0
    for application in pending:
        application.status = RegistryApplicationStatus.PUBLISHED.value
        application.published_manifest_serial = serial
        application.published_at = now
    RegistryApplication.objects.bulk_update(
        pending,
        ["status", "published_manifest_serial", "published_at"],
    )
    return len(pending)


@transaction.atomic
def publish_registry_manifest_via_sync(*, dry_run: bool = False) -> PublishResult:
    client = FederationSyncClient.from_settings()
    sites = build_sync_publish_site_entries()
    min_serial = _min_serial_for_sync_publish()
    try:
        data = client.publish(sites, min_serial, dry_run)
    except SyncUnavailableError as exc:
        return PublishResult(ok=False, message=str(exc))

    serial = int(data.get("serial", -1))
    site_names = data.get("site_names") or []
    if dry_run:
        return PublishResult(
            ok=True,
            message=(
                f"Dry run: would publish serial {serial} "
                f"with {len(site_names)} sites via federation sync."
            ),
            serial=serial,
        )

    now = timezone.now()
    marked = _mark_applications_published(serial, now)
    site_word = "site" if marked == 1 else "sites"
    return PublishResult(
        ok=True,
        message=(
            f"Published registry manifest serial {serial} via federation sync "
            f"({len(site_names)} members; marked {marked} approved {site_word} published)."
        ),
        serial=serial,
    )
