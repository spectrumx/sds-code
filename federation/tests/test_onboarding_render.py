"""Template render smoke tests (no writes under federation/)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = FEDERATION_ROOT / "templates" / "federation.toml.tmpl"


@pytest.mark.regression
def test_federation_toml_template_omits_ca_without_peer_ca() -> None:
    env = {
        **os.environ,
        "SDS_SITE_NAME": "crc",
        "SDS_SITE_FQDN": "sds.crc.nd.edu",
        "SDS_SITE_DISPLAY_NAME": "CRC",
        "FEDERATION_SYNC_SERVICE_URL": "https://sds.crc.nd.edu/sync",
        "FEDERATION_PEER_NAME": "crc",
        "FEDERATION_PEER_FQDN": "sds.crc.nd.edu",
        "FEDERATION_PEER_DISPLAY_NAME": "CRC",
        "FEDERATION_PEER_GATEWAY_API_BASE": "https://sds.crc.nd.edu/api/v1",
        "FEDERATION_PEER_SYNC_SERVICE_URL": "https://sds.crc.nd.edu/sync/",
    }
    result = subprocess.run(
        ["envsubst"],
        input=TEMPLATE.read_text(encoding="utf-8"),
        cwd=FEDERATION_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert 'name = "crc"' in result.stdout
    assert "ca_cert_path" not in result.stdout


@pytest.mark.regression
def test_federation_toml_template_local_peer_uses_docker_dns() -> None:
    env = {
        **os.environ,
        "SDS_SITE_NAME": "crc",
        "SDS_SITE_FQDN": "sds.localhost",
        "SDS_SITE_DISPLAY_NAME": "Local CRC",
        "FEDERATION_SYNC_SERVICE_URL": "http://localhost:8001/sync",
        "FEDERATION_PEER_NAME": "peer",
        "FEDERATION_PEER_FQDN": "peer.local",
        "FEDERATION_PEER_DISPLAY_NAME": "Local Peer",
        "FEDERATION_PEER_GATEWAY_API_BASE": "http://sds-gateway-local-app:8000/api/v1",
        "FEDERATION_PEER_SYNC_SERVICE_URL": "http://sds-federation-peer-sync:8000/sync",
    }
    result = subprocess.run(
        ["envsubst"],
        input=TEMPLATE.read_text(encoding="utf-8"),
        cwd=FEDERATION_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "sds-federation-peer-sync:8000/sync" in result.stdout
