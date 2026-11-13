"""Staff workflow: publish signed registry manifest via federation sync."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_manifest import ManifestBuildError
from sds_gateway.api_methods.federation.registry_manifest import build_manifest_site_list
from sds_gateway.api_methods.federation.registry_manifest import manifest_min_serial
from sds_gateway.api_methods.federation.registry_manifest import manifest_peer_site_names
from sds_gateway.api_methods.federation.sync_client import FederationSyncClient
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_PUBLISH_ENABLED_CACHE_KEY = "federation_registry_publish_enabled"
_PUBLISH_ENABLED_CACHE_SECS = 30

_PUBLISH_DISABLED_MESSAGE = (
    "Registry publish is not enabled on federation sync "
    "(signing key or [registry.publish] missing)."
)
_SYNC_UNAVAILABLE_MESSAGE = (
    "Federation sync is unavailable. Try again after sync is healthy."
)


@dataclass(frozen=True, slots=True)
class StaffOpResult:
    ok: bool
    message: str
    serial: int | None = None
    site_names: tuple[str, ...] = ()


def registry_sync_publish_enabled(*, force_refresh: bool = False) -> bool:
    """Whether flagship sync can sign and publish the registry manifest."""
    if not force_refresh:
        cached = cache.get(_PUBLISH_ENABLED_CACHE_KEY)
        if cached is not None:
            return bool(cached)
    try:
        client = FederationSyncClient.from_settings()
        payload = client.capabilities()
        enabled = bool(payload.get("publish_enabled"))
    except SyncUnavailableError:
        enabled = False
    cache.set(_PUBLISH_ENABLED_CACHE_KEY, enabled, _PUBLISH_ENABLED_CACHE_SECS)
    return enabled


def publish_registry_manifest(*, dry_run: bool = False) -> StaffOpResult:
    """Build site list from DB, publish on sync, mark approved rows published."""
    if not registry_sync_publish_enabled(force_refresh=True):
        return StaffOpResult(ok=False, message=_PUBLISH_DISABLED_MESSAGE)

    try:
        sites = build_manifest_site_list()
    except ManifestBuildError as exc:
        return StaffOpResult(ok=False, message=str(exc))

    peer_names = manifest_peer_site_names(sites)
    if not peer_names:
        return StaffOpResult(
            ok=False,
            message=(
                "No approved or published registry applications with a site id. "
                "Approve an application before publishing."
            ),
        )

    min_serial = manifest_min_serial()
    try:
        client = FederationSyncClient.from_settings()
        payload = client.publish(sites, min_serial=min_serial, dry_run=dry_run)
    except SyncUnavailableError as exc:
        return StaffOpResult(ok=False, message=str(exc) or _SYNC_UNAVAILABLE_MESSAGE)

    serial = int(payload["serial"])
    names = tuple(str(n) for n in payload.get("site_names") or peer_names)
    if dry_run:
        name_list = ", ".join(names) if names else "(none)"
        return StaffOpResult(
            ok=True,
            message=f"Dry run: manifest serial would be {serial} ({name_list}).",
            serial=serial,
            site_names=names,
        )

    now = timezone.now()
    with transaction.atomic():
        updated = RegistryApplication.objects.filter(site_name__in=peer_names).update(
            status=RegistryApplicationStatus.PUBLISHED.value,
            published_manifest_serial=serial,
            published_at=now,
        )
    if updated == 0:
        msg = "Manifest published on sync but no matching applications were updated."
        return StaffOpResult(ok=False, message=msg, serial=serial, site_names=names)

    name_list = ", ".join(names)
    return StaffOpResult(
        ok=True,
        message=f"Published registry manifest serial {serial} ({name_list}).",
        serial=serial,
        site_names=names,
    )
