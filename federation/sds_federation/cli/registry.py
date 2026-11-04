"""Registry CLI: fingerprint, publish from JSON, optional key generation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sds_federation.models import load_federation_config
from sds_federation.schemas.registry import RegistrySite
from sds_federation.services.registry_publish import publish_manifest
from sds_federation.services.registry_sign import RegistrySignError
from sds_federation.services.registry_sign import registry_public_key_fingerprint


def _cmd_fingerprint(args: argparse.Namespace) -> int:
    path = args.public_key_path
    if not path:
        config = load_federation_config()
        path = config.registry.public_key_path.strip()
    if not path:
        print("public key path is required", file=sys.stderr)
        return 1
    try:
        print(registry_public_key_fingerprint(path))
    except RegistrySignError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def _cmd_publish(args: argparse.Namespace) -> int:
    config = load_federation_config()
    raw = Path(args.sites_json).read_text(encoding="utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, list):
        print("sites JSON must be a list of site objects", file=sys.stderr)
        return 1
    sites = [RegistrySite.model_validate(item) for item in payload]
    try:
        result = publish_manifest(
            config,
            sites,
            args.min_serial,
            dry_run=args.dry_run,
        )
    except RegistrySignError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_keygen(args: argparse.Namespace) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    private_key = Ed25519PrivateKey.generate()
    sign_path = out_dir / "sign.pem"
    pub_path = out_dir / "registry.pub.pem"
    sign_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub_path.write_bytes(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"wrote {sign_path} and {pub_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sds_federation.cli.registry")
    sub = parser.add_subparsers(dest="command", required=True)

    fp = sub.add_parser(
        "fingerprint", help="Print sha256 fingerprint of registry public key"
    )
    fp.add_argument("--public-key-path", default="")
    fp.set_defaults(func=_cmd_fingerprint)

    pub = sub.add_parser(
        "publish", help="Sign and write registry manifest on this sync host"
    )
    pub.add_argument(
        "--sites-json", required=True, help="JSON file: list of RegistrySite objects"
    )
    pub.add_argument("--min-serial", type=int, default=None)
    pub.add_argument("--dry-run", action="store_true")
    pub.set_defaults(func=_cmd_publish)

    kg = sub.add_parser("keygen", help="Generate Ed25519 sign.pem + registry.pub.pem")
    kg.add_argument("--out-dir", required=True)
    kg.set_defaults(func=_cmd_keygen)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
