"""Build and sign federation registry sites.json on the flagship gateway."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from sds_gateway.api_methods.federation.registry_manifest_publish import (
    RegistryManifestPublishError,
)
from sds_gateway.api_methods.federation.registry_manifest_publish import (
    publish_registry_manifest,
)


class Command(BaseCommand):
    help = (
        "Build, sign, and publish /.well-known/sds-registry/sites.json on the "
        "flagship gateway (requires FEDERATION_REGISTRY_SIGNING_KEY_PATH)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Build and sign without writing files or updating applications.",
        )
        parser.add_argument(
            "--signing-key-path",
            default="",
            help="Override FEDERATION_REGISTRY_SIGNING_KEY_PATH for this run.",
        )

    def handle(self, *args, **options) -> None:
        signing_key = (options["signing_key_path"] or "").strip() or None
        try:
            result = publish_registry_manifest(
                dry_run=bool(options["dry_run"]),
                signing_key_path=signing_key,
            )
        except RegistryManifestPublishError as exc:
            raise CommandError(str(exc)) from exc
        if result.ok:
            self.stdout.write(self.style.SUCCESS(result.message))
            if result.storage_dir:
                self.stdout.write(f"storage_dir={result.storage_dir}")
        else:
            raise CommandError(result.message)
