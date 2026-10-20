"""Publish signed sites.json + sites.json.sig on the flagship gateway."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from config.settings.utils import is_flagship_gateway_deployment
from sds_gateway.api_methods.federation.registry_manifest_build import build_manifest_dict
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    MANIFEST_FILENAME,
    SERIAL_FILENAME,
    SIGNATURE_FILENAME,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    RegistryManifestSignError,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    canonical_manifest_json_bytes,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    encode_signature_for_well_known,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    load_signing_private_key,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import sign_manifest_payload
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@dataclass(frozen=True, slots=True)
class PublishResult:
    ok: bool
    message: str
    serial: int | None = None
    storage_dir: str | None = None


class RegistryManifestPublishError(Exception):
    """Precondition failed for manifest publication."""


def resolve_manifest_storage_dir() -> Path:
    raw = str(
        getattr(settings, "FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR", "") or ""
    ).strip()
    if raw:
        return Path(raw)
    base = getattr(settings, "BASE_DIR", None)
    if base is None:
        msg = "FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR is not configured"
        raise RegistryManifestPublishError(msg)
    return Path(base) / "registry_manifest"


def read_published_serial(storage_dir: Path) -> int:
    serial_path = storage_dir / SERIAL_FILENAME
    if serial_path.is_file():
        try:
            return int(serial_path.read_text(encoding="utf-8").strip())
        except ValueError:
            return -1
    from_db = (
        RegistryApplication.objects.filter(published_manifest_serial__isnull=False)
        .order_by("-published_manifest_serial")
        .values_list("published_manifest_serial", flat=True)
        .first()
    )
    if from_db is not None:
        return int(from_db)
    return -1


def next_manifest_serial(storage_dir: Path) -> int:
    return read_published_serial(storage_dir) + 1


def assert_can_publish_manifest() -> None:
    if not is_flagship_gateway_deployment(
        site_fqdn=str(getattr(settings, "SDS_SITE_FQDN", "") or ""),
        flagship_gateway_host=str(getattr(settings, "FLAGSHIP_GATEWAY_HOST", "") or ""),
    ):
        msg = (
            "registry manifest publish is only allowed when SDS_SITE_FQDN matches "
            "FLAGSHIP_GATEWAY_HOST"
        )
        raise RegistryManifestPublishError(msg)
    key_path = str(
        getattr(settings, "FEDERATION_REGISTRY_SIGNING_KEY_PATH", "") or ""
    ).strip()
    if not key_path:
        msg = "FEDERATION_REGISTRY_SIGNING_KEY_PATH is not set"
        raise RegistryManifestPublishError(msg)


def _write_manifest_files(
    storage_dir: Path,
    payload: bytes,
    signature_b64: bytes,
    serial: int,
) -> None:
    storage_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = storage_dir / MANIFEST_FILENAME
    sig_path = storage_dir / SIGNATURE_FILENAME
    serial_path = storage_dir / SERIAL_FILENAME

    tmp_manifest = manifest_path.with_suffix(".json.tmp")
    tmp_sig = sig_path.with_suffix(".sig.tmp")
    tmp_manifest.write_bytes(payload)
    tmp_sig.write_bytes(signature_b64)
    tmp_manifest.replace(manifest_path)
    tmp_sig.replace(sig_path)
    serial_path.write_text(str(serial), encoding="utf-8")


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
def publish_registry_manifest(
    *,
    dry_run: bool = False,
    signing_key_path: str | None = None,
) -> PublishResult:
    """Build, sign, and write sites.json (+ .sig) for peer polling."""
    assert_can_publish_manifest()
    storage_dir = resolve_manifest_storage_dir()
    serial = next_manifest_serial(storage_dir)
    manifest = build_manifest_dict(serial=serial)
    payload = canonical_manifest_json_bytes(manifest)

    key_path = (
        signing_key_path
        or str(getattr(settings, "FEDERATION_REGISTRY_SIGNING_KEY_PATH", "") or "").strip()
    )
    try:
        private_key = load_signing_private_key(key_path)
        signature = sign_manifest_payload(payload, private_key)
    except RegistryManifestSignError as exc:
        return PublishResult(ok=False, message=str(exc))

    signature_b64 = encode_signature_for_well_known(signature)
    if dry_run:
        return PublishResult(
            ok=True,
            message=(
                f"Dry run: would publish serial {serial} "
                f"with {len(manifest['sites'])} sites."
            ),
            serial=serial,
            storage_dir=str(storage_dir),
        )

    _write_manifest_files(storage_dir, payload, signature_b64, serial)
    now = timezone.now()
    marked = _mark_applications_published(serial, now)
    site_word = "site" if marked == 1 else "sites"
    return PublishResult(
        ok=True,
        message=(
            f"Published registry manifest serial {serial} "
            f"({len(manifest['sites'])} members; marked {marked} approved {site_word} published)."
        ),
        serial=serial,
        storage_dir=str(storage_dir),
    )


def read_published_manifest_bytes(storage_dir: Path | None = None) -> bytes | None:
    directory = storage_dir or resolve_manifest_storage_dir()
    path = directory / MANIFEST_FILENAME
    if not path.is_file():
        return None
    return path.read_bytes()


def read_published_signature_bytes(storage_dir: Path | None = None) -> bytes | None:
    directory = storage_dir or resolve_manifest_storage_dir()
    path = directory / SIGNATURE_FILENAME
    if not path.is_file():
        return None
    return path.read_bytes()
