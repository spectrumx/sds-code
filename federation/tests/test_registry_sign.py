from __future__ import annotations

from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_sign import canonical_manifest_json_bytes
from sds_federation.services.registry_sign import encode_signature_for_well_known
from sds_federation.services.registry_sign import load_signing_private_key
from sds_federation.services.registry_sign import registry_public_key_fingerprint
from sds_federation.services.registry_sign import sign_manifest_payload
from sds_federation.services.registry_sign import verify_manifest_payload


def write_ed25519_keypair(directory: Path) -> tuple[Path, Path]:
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


def test_canonical_manifest_json_is_stable() -> None:
    manifest = {
        "schema_version": 1,
        "serial": 1,
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-01-08T00:00:00Z",
        "sites": [],
    }
    first = canonical_manifest_json_bytes(manifest)
    second = canonical_manifest_json_bytes(manifest)
    assert first == second


def test_sign_and_verify_round_trip(tmp_path: Path) -> None:
    private_path, public_path = write_ed25519_keypair(tmp_path)
    payload = canonical_manifest_json_bytes(
        {"schema_version": 1, "serial": 0, "sites": []},
    )
    private_key = load_signing_private_key(private_path)
    signature = sign_manifest_payload(payload, private_key)
    sig_b64 = encode_signature_for_well_known(signature)
    verify_manifest_payload(payload, sig_b64, public_path)


def test_load_signing_private_key_missing(tmp_path: Path) -> None:
    with pytest.raises(RegistrySignError, match="not found"):
        load_signing_private_key(tmp_path / "missing.pem")


def test_fingerprint_prefix(tmp_path: Path) -> None:
    _, public_path = write_ed25519_keypair(tmp_path)
    fingerprint = registry_public_key_fingerprint(public_path)
    assert fingerprint.startswith("sha256:")
