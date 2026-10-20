"""Print sha256 fingerprint of the federation registry Ed25519 public key."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from sds_gateway.api_methods.federation.registry_manifest_sign import (
    RegistryManifestSignError,
)
from sds_gateway.api_methods.federation.registry_manifest_sign import (
    registry_public_key_fingerprint,
)


class Command(BaseCommand):
    help = "Print registry_pubkey_fingerprint for well-known JSON and peer federation.toml."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--public-key-path",
            default="",
            help="Override FEDERATION_REGISTRY_PUBLIC_KEY_PATH.",
        )

    def handle(self, *args, **options) -> None:
        path = (options["public_key_path"] or "").strip() or str(
            getattr(settings, "FEDERATION_REGISTRY_PUBLIC_KEY_PATH", "") or ""
        ).strip()
        if not path:
            raise CommandError(
                "Set FEDERATION_REGISTRY_PUBLIC_KEY_PATH or pass --public-key-path.",
            )
        try:
            fingerprint = registry_public_key_fingerprint(path)
        except RegistryManifestSignError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(fingerprint)
