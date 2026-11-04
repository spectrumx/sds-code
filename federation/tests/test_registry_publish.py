from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import AnyHttpUrl
from sds_federation.models import FederationConfig
from sds_federation.models import RegistryPolicy
from sds_federation.models import RegistryPublishPolicy
from sds_federation.models import SiteInfo
from sds_federation.schemas.registry import RegistrySite
from sds_federation.services.registry_publish import publish_manifest
from sds_federation.services.registry_sign import MANIFEST_FILENAME
from sds_federation.services.registry_sign import SERIAL_FILENAME
from sds_federation.services.registry_sign import SIGNATURE_FILENAME
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_sign import verify_manifest_payload
from sds_federation.services.site_registry import _accept

from tests.test_registry_sign import write_ed25519_keypair


def _flagship_config(
    tmp_path: Path,
    *,
    private_path: Path,
    enabled: bool = True,
) -> FederationConfig:
    manifest_dir = tmp_path / "publish"
    return FederationConfig(
        site=SiteInfo(
            name="crc",
            fqdn="sds.crc.nd.edu",
            display_name="CRC SDS",
            gateway_api_base=AnyHttpUrl("https://sds.crc.nd.edu/api/v1"),
            sync_service_url=AnyHttpUrl("https://sds.crc.nd.edu/sync"),
        ),
        gateway_api_base="https://sds.crc.nd.edu/api/v1",
        sync_service_url="https://sds.crc.nd.edu/sync",
        peers=[],
        registry=RegistryPolicy(
            public_key_path=str(tmp_path / "registry.pub.pem"),
            cache_dir=str(tmp_path / "cache"),
            publish=RegistryPublishPolicy(
                enabled=enabled,
                signing_key_path=str(private_path),
                manifest_dir=str(manifest_dir),
                ttl_hours=168,
            ),
        ),
    )


def test_publish_writes_files_and_includes_flagship_and_peer(
    tmp_path: Path,
) -> None:
    private_path, public_path = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    peer = RegistrySite(
        name="peer",
        fqdn="peer.example.edu",
        display_name="Peer",
        gateway_api_base=AnyHttpUrl("https://peer.example.edu/api/v1"),
        sync_service_url=AnyHttpUrl("https://peer.example.edu/sync"),
    )
    result = publish_manifest(config, [peer], min_serial=None, dry_run=False)
    assert result["serial"] == 0
    assert set(result["site_names"]) == {"crc", "peer"}

    manifest_path = Path(config.registry.publish.manifest_dir) / MANIFEST_FILENAME
    sig_path = Path(config.registry.publish.manifest_dir) / SIGNATURE_FILENAME
    serial_path = Path(config.registry.publish.manifest_dir) / SERIAL_FILENAME
    payload = manifest_path.read_bytes()
    sig_b64 = sig_path.read_bytes()
    verify_manifest_payload(payload, sig_b64, public_path)
    assert serial_path.read_text(encoding="utf-8") == "0"
    data = json.loads(payload.decode())
    assert data["serial"] == 0


def test_publish_increments_serial(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    first = publish_manifest(config, [], None, dry_run=False)
    second = publish_manifest(config, [], None, dry_run=False)
    assert first["serial"] == 0
    assert second["serial"] == 1


def test_publish_min_serial_seeding(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    result = publish_manifest(config, [], min_serial=5, dry_run=False)
    assert result["serial"] == 5


def test_publish_dry_run_writes_nothing(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    publish_manifest(config, [], None, dry_run=True)
    manifest_path = Path(config.registry.publish.manifest_dir) / MANIFEST_FILENAME
    assert not manifest_path.is_file()


def test_publish_missing_key_raises(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    config.registry.publish.signing_key_path = str(tmp_path / "missing.pem")
    with pytest.raises(RegistrySignError, match="not found"):
        publish_manifest(config, [], None, dry_run=False)


def test_published_manifest_passes_site_registry_accept(tmp_path: Path) -> None:
    private_path, _public_path = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    publish_manifest(config, [], None, dry_run=False)
    manifest_path = Path(config.registry.publish.manifest_dir) / MANIFEST_FILENAME
    sig_path = Path(config.registry.publish.manifest_dir) / SIGNATURE_FILENAME
    payload = manifest_path.read_bytes()
    import base64

    signature = base64.b64decode(sig_path.read_bytes().strip(), validate=True)
    manifest = _accept(
        config.registry, payload, signature, now=datetime(2020, 1, 1, tzinfo=UTC)
    )
    assert manifest.serial == 0


def _extra_site(name: str, fqdn: str) -> RegistrySite:
    return RegistrySite(
        name=name,
        fqdn=fqdn,
        display_name=name,
        gateway_api_base=AnyHttpUrl(f"https://{fqdn}/api/v1"),
        sync_service_url=AnyHttpUrl(f"https://{fqdn}/sync"),
    )


def test_extra_site_cannot_override_flagship_by_name(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    result = publish_manifest(
        config, [_extra_site("crc", "evil.example.edu")], None, dry_run=False
    )
    assert result["site_names"] == ["crc"]
    manifest_dir = Path(config.registry.publish.manifest_dir)
    data = json.loads((manifest_dir / MANIFEST_FILENAME).read_bytes())
    assert data["sites"][0]["fqdn"] == "sds.crc.nd.edu"


def test_duplicate_site_names_rejected(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    sites = [_extra_site("dup", "a.example.edu"), _extra_site("dup", "b.example.edu")]
    with pytest.raises(ValueError, match="unique names"):
        publish_manifest(config, sites, None, dry_run=False)


def test_corrupt_serial_file_does_not_roll_back_serial(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    publish_manifest(config, [], min_serial=7, dry_run=False)
    manifest_dir = Path(config.registry.publish.manifest_dir)
    (manifest_dir / SERIAL_FILENAME).write_text("", encoding="utf-8")
    assert publish_manifest(config, [], None, dry_run=False)["serial"] == 8


def test_dry_run_has_no_filesystem_side_effects(tmp_path: Path) -> None:
    private_path, _ = write_ed25519_keypair(tmp_path)
    config = _flagship_config(tmp_path, private_path=private_path)
    result = publish_manifest(config, [], None, dry_run=True)
    assert result["dry_run"] is True
    assert not Path(config.registry.publish.manifest_dir).exists()
