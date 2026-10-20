"""Ed25519 signing for federation registry sites.json (raw bytes + base64 .sig)."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import PublicFormat
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from cryptography.hazmat.primitives.serialization import load_pem_public_key

REGISTRY_MANIFEST_SCHEMA_VERSION = 1

MANIFEST_FILENAME = "sites.json"
SIGNATURE_FILENAME = "sites.json.sig"
SERIAL_FILENAME = "serial"


class RegistryManifestSignError(Exception):
    """Invalid key material or signature verification failure."""


def canonical_manifest_json_bytes(manifest: dict[str, Any]) -> bytes:
    """Stable UTF-8 JSON suitable for signing (must match served sites.json bytes)."""
    return json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def load_signing_private_key(path: str | Path) -> Ed25519PrivateKey:
    pem_path = Path(path)
    if not pem_path.is_file():
        msg = f"registry signing key not found: {pem_path}"
        raise RegistryManifestSignError(msg)
    key = load_pem_private_key(pem_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        msg = f"registry signing key at {pem_path} is not Ed25519"
        raise RegistryManifestSignError(msg)
    return key


def load_verifying_public_key(path: str | Path) -> Ed25519PublicKey:
    pem_path = Path(path)
    if not pem_path.is_file():
        msg = f"registry public key not found: {pem_path}"
        raise RegistryManifestSignError(msg)
    key = load_pem_public_key(pem_path.read_bytes())
    if not isinstance(key, Ed25519PublicKey):
        msg = f"registry public key at {pem_path} is not Ed25519"
        raise RegistryManifestSignError(msg)
    return key


def sign_manifest_payload(payload: bytes, private_key: Ed25519PrivateKey) -> bytes:
    return private_key.sign(payload)


def encode_signature_for_well_known(signature: bytes) -> bytes:
    return base64.b64encode(signature)


def decode_signature_from_well_known(raw: bytes) -> bytes:
    return base64.b64decode(raw.strip(), validate=True)


def verify_manifest_payload(
    payload: bytes,
    signature_b64: bytes,
    public_key_pem_path: str | Path,
) -> None:
    public_key = load_verifying_public_key(public_key_pem_path)
    signature = decode_signature_from_well_known(signature_b64)
    try:
        public_key.verify(signature, payload)
    except InvalidSignature as exc:
        raise RegistryManifestSignError("registry signature verification failed") from exc


def registry_public_key_fingerprint(public_key_pem_path: str | Path) -> str:
    public_key = load_verifying_public_key(public_key_pem_path)
    der = public_key.public_bytes(
        encoding=Encoding.DER,
        format=PublicFormat.SubjectPublicKeyInfo,
    )
    return f"sha256:{hashlib.sha256(der).hexdigest()}"
