from __future__ import annotations

import json
from http import HTTPStatus
from typing import TYPE_CHECKING

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from django.urls import reverse

from sds_gateway.api_methods.federation.registry_manifest_publish import (
    publish_registry_manifest,
)

if TYPE_CHECKING:
    from pathlib import Path


def _write_ed25519_keypair(directory: Path) -> Path:
    private_key = Ed25519PrivateKey.generate()
    private_path = directory / "registry-sign.pem"
    private_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    return private_path


@pytest.mark.django_db
def test_registry_manifest_well_known_endpoints(
    settings, client, tmp_path: Path
) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_SITE_NAME = "crc"
    settings.SDS_SITE_DISPLAY_NAME = "CRC"
    settings.FEDERATION_REGISTRY_MANIFEST_STORAGE_DIR = str(tmp_path / "manifest")
    settings.FEDERATION_REGISTRY_SIGNING_KEY_PATH = str(
        _write_ed25519_keypair(tmp_path),
    )

    missing_manifest = client.get(reverse("sds_registry_manifest"))
    assert missing_manifest.status_code == HTTPStatus.NOT_FOUND

    publish_registry_manifest()
    manifest_response = client.get(reverse("sds_registry_manifest"))
    sig_response = client.get(reverse("sds_registry_manifest_signature"))
    assert manifest_response.status_code == HTTPStatus.OK
    assert sig_response.status_code == HTTPStatus.OK
    assert json.loads(manifest_response.content)["schema_version"] == 1
    assert manifest_response["Content-Type"].startswith("application/json")
