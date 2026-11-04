"""Golden fixtures: stable manifest bytes signed with a fixed test keypair."""

from __future__ import annotations

from pathlib import Path

from sds_federation.services.registry_sign import canonical_manifest_json_bytes
from sds_federation.services.registry_sign import encode_signature_for_well_known
from sds_federation.services.registry_sign import load_signing_private_key
from sds_federation.services.registry_sign import sign_manifest_payload
from sds_federation.services.registry_sign import verify_manifest_payload

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "registry"


def test_golden_fixture_verifies_with_public_key() -> None:
    payload = (FIXTURES / "sites.json").read_bytes()
    sig_b64 = (FIXTURES / "sites.json.sig").read_bytes()
    verify_manifest_payload(payload, sig_b64, FIXTURES / "registry.pub.pem")


def test_golden_fixture_matches_canonical_builder() -> None:
    payload = (FIXTURES / "sites.json").read_bytes()
    import json

    expected = json.loads(payload.decode())
    rebuilt = canonical_manifest_json_bytes(expected)
    assert rebuilt == payload


def test_golden_signing_key_matches_fixture(tmp_path: Path) -> None:
    """Regenerate signature from fixture manifest + sign.pem; must match sites.json.sig."""
    payload = (FIXTURES / "sites.json").read_bytes()
    private_key = load_signing_private_key(FIXTURES / "sign.pem")
    signature = sign_manifest_payload(payload, private_key)
    assert encode_signature_for_well_known(signature) == (
        FIXTURES / "sites.json.sig"
    ).read_bytes()
