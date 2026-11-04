from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_manifest_publish import (
    RegistryManifestPublishError,
)
from sds_gateway.api_methods.federation.registry_manifest_publish import (
    publish_registry_manifest,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    verify_manifest_payload,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


def _write_ed25519_keypair(directory: Path) -> tuple[Path, Path]:
    private_key = Ed25519PrivateKey.generate()
    private_path = directory / "registry-sign.pem"
    public_path = directory / "registry.pub.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return private_path, public_path


@pytest.mark.django_db
def test_publish_manifest_writes_files_and_marks_applications(
    settings,
    tmp_path: Path,
    user,
) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_SITE_NAME = "crc"
    settings.SDS_SITE_DISPLAY_NAME = "CRC SDS"
    settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR = str(tmp_path / "manifest")
    private_path, public_path = _write_ed25519_keypair(tmp_path)
    settings.FEDERATION_REGISTRY_SIGNING_KEY_PATH = str(private_path)

    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        site_name="peer",
        gateway_api_base="https://peer.example.edu/api/v1",
        sync_service_url="https://peer.example.edu/sync",
        challenge_token_hash=hash_registry_challenge_token("publish-test"),
        status=RegistryApplicationStatus.APPROVED.value,
    )

    result = publish_registry_manifest()
    assert result.ok
    assert result.serial == 0

    manifest_path = (
        Path(settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR) / "sites.json"
    )
    sig_path = manifest_path.with_suffix(".json.sig")
    payload = manifest_path.read_bytes()
    sig_b64 = sig_path.read_bytes()
    verify_manifest_payload(payload, sig_b64, public_path)

    data = json.loads(payload.decode())
    assert data["serial"] == 0
    site_names = {site["name"] for site in data["sites"]}
    assert site_names == {"crc", "peer"}

    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PUBLISHED.value
    assert application.published_manifest_serial == 0
    assert application.published_at is not None


@pytest.mark.django_db
def test_publish_increments_serial(settings, tmp_path: Path) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_SITE_NAME = "crc"
    settings.SDS_SITE_DISPLAY_NAME = "CRC"
    storage = tmp_path / "manifest"
    settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR = str(storage)
    private_path, _ = _write_ed25519_keypair(tmp_path)
    settings.FEDERATION_REGISTRY_SIGNING_KEY_PATH = str(private_path)

    first = publish_registry_manifest()
    second = publish_registry_manifest()
    assert first.serial == 0
    assert second.serial == 1


@pytest.mark.django_db
def test_publish_rejects_non_flagship(settings, tmp_path: Path) -> None:
    settings.SDS_SITE_FQDN = "peer.example.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_REGISTRY_SIGNING_KEY_PATH = str(
        _write_ed25519_keypair(tmp_path)[0],
    )
    with pytest.raises(RegistryManifestPublishError):
        publish_registry_manifest()


@pytest.mark.django_db
def test_pydantic_manifest_round_trip(settings, tmp_path: Path) -> None:
    pytest.importorskip("sds_federation")
    from sds_federation.schemas.registry import RegistryManifest

    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_SITE_NAME = "crc"
    settings.SDS_SITE_DISPLAY_NAME = "CRC"
    settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR = str(tmp_path / "manifest")
    private_path, public_path = _write_ed25519_keypair(tmp_path)
    settings.FEDERATION_REGISTRY_SIGNING_KEY_PATH = str(private_path)

    publish_registry_manifest()
    payload = (
        Path(settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR) / "sites.json"
    ).read_bytes()
    sig = (
        Path(settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR) / "sites.json.sig"
    ).read_bytes()
    verify_manifest_payload(payload, sig, public_path)
    manifest = RegistryManifest.model_validate(json.loads(payload))
    assert manifest.serial == 0
    assert len(manifest.active_sites()) >= 1
    assert not manifest.is_expired(now=timezone.now())
