"""Unit tests for registry manifest trust checks (_accept, cache round-trip)."""

from __future__ import annotations

import json
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from sds_federation.models import RegistryPolicy
from sds_federation.schemas.registry import REGISTRY_SCHEMA_VERSION
from sds_federation.services.site_registry import RegistryTrustError
from sds_federation.services.site_registry import _accept
from sds_federation.services.site_registry import _cache
from sds_federation.services.site_registry import load_cached_manifest


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


def _manifest_payload(
    *,
    serial: int,
    extra_site: dict | None = None,
    issued: datetime | None = None,
) -> bytes:
    anchor = issued or datetime.now(UTC)
    sites = [
        {
            "name": "crc",
            "fqdn": "sds.crc.nd.edu",
            "display_name": "CRC",
            "status": "active",
            "gateway_api_base": "https://sds.crc.nd.edu/api/v1",
            "sync_service_url": "https://sds.crc.nd.edu/sync",
        }
    ]
    if extra_site:
        sites.append(extra_site)
    body = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "serial": serial,
        "issued_at": anchor.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (anchor + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sites": sites,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(payload: bytes, private_path: Path) -> bytes:
    private_key = serialization.load_pem_private_key(
        private_path.read_bytes(),
        password=None,
    )
    assert isinstance(private_key, Ed25519PrivateKey)
    return private_key.sign(payload)


def _policy(tmp_path: Path, public_path: Path) -> RegistryPolicy:
    cache = tmp_path / "cache"
    cache.mkdir()
    return RegistryPolicy(
        public_key_path=str(public_path),
        cache_dir=str(cache),
    )


def test_accept_valid_manifest_and_cache_round_trip(tmp_path: Path) -> None:
    _, public_path = _write_ed25519_keypair(tmp_path)
    private_path = tmp_path / "registry-sign.pem"
    policy = _policy(tmp_path, public_path)
    payload = _manifest_payload(serial=0)
    signature = _sign(payload, private_path)

    manifest = _accept(policy, payload, signature, now=datetime.now(UTC))
    assert manifest.serial == 0

    _cache(policy, payload, signature, manifest.serial)
    restored = load_cached_manifest(policy)
    assert restored is not None
    assert restored.serial == 0


def test_accept_rejects_serial_rollback(tmp_path: Path) -> None:
    _, public_path = _write_ed25519_keypair(tmp_path)
    private_path = tmp_path / "registry-sign.pem"
    policy = _policy(tmp_path, public_path)
    payload0 = _manifest_payload(serial=0)
    sig0 = _sign(payload0, private_path)
    _cache(policy, payload0, sig0, 0)

    payload1 = _manifest_payload(serial=1)
    sig1 = _sign(payload1, private_path)
    _accept(policy, payload1, sig1, now=datetime.now(UTC))
    _cache(policy, payload1, sig1, 1)

    with pytest.raises(RegistryTrustError, match="older than accepted"):
        _accept(policy, payload0, sig0, now=datetime.now(UTC))


def test_accept_rejects_equal_serial_with_different_bytes(tmp_path: Path) -> None:
    _, public_path = _write_ed25519_keypair(tmp_path)
    private_path = tmp_path / "registry-sign.pem"
    policy = _policy(tmp_path, public_path)
    issued = datetime.now(UTC)
    payload = _manifest_payload(serial=1, issued=issued)
    signature = _sign(payload, private_path)
    _cache(policy, payload, signature, 1)

    tampered = _manifest_payload(
        serial=1,
        issued=issued,
        extra_site={
            "name": "fed1",
            "fqdn": "fed1.test",
            "display_name": "Fed1",
            "status": "active",
            "gateway_api_base": "https://fed1.test/api/v1",
            "sync_service_url": "https://fed1.test/sync",
        },
    )
    bad_sig = _sign(tampered, private_path)
    check_now = issued + timedelta(hours=1)

    with pytest.raises(RegistryTrustError, match="reused with different manifest bytes"):
        _accept(policy, tampered, bad_sig, now=check_now)


def test_accept_allows_equal_serial_with_identical_bytes(tmp_path: Path) -> None:
    _, public_path = _write_ed25519_keypair(tmp_path)
    private_path = tmp_path / "registry-sign.pem"
    policy = _policy(tmp_path, public_path)
    payload = _manifest_payload(serial=2)
    signature = _sign(payload, private_path)
    _cache(policy, payload, signature, 2)

    again = _accept(policy, payload, signature, now=datetime.now(UTC))
    assert again.serial == 2


def test_accept_rejects_bad_signature(tmp_path: Path) -> None:
    _, public_path = _write_ed25519_keypair(tmp_path)
    private_path = tmp_path / "registry-sign.pem"
    policy = _policy(tmp_path, public_path)
    payload = _manifest_payload(serial=0)
    signature = _sign(payload, private_path)

    with pytest.raises(RegistryTrustError, match="signature verification failed"):
        _accept(policy, payload + b"x", signature, now=datetime.now(UTC))


def test_accept_rejects_expired_manifest(tmp_path: Path) -> None:
    _, public_path = _write_ed25519_keypair(tmp_path)
    private_path = tmp_path / "registry-sign.pem"
    policy = _policy(tmp_path, public_path)
    past = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    body = {
        "schema_version": REGISTRY_SCHEMA_VERSION,
        "serial": 0,
        "issued_at": past.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "expires_at": (past + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sites": [],
    }
    payload = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = _sign(payload, private_path)

    with pytest.raises(RegistryTrustError, match="expired"):
        _accept(
            policy,
            payload,
            signature,
            now=datetime(2026, 1, 1, tzinfo=UTC),
        )
