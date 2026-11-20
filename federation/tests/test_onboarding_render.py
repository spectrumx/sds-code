"""Template render smoke tests (no writes under federation/)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = FEDERATION_ROOT / "templates" / "federation.toml.tmpl"
_ENVSUBST_PATTERN = re.compile(r"\$\{([^}]+)\}")


def envsubst_template(text: str, env: dict[str, str]) -> str:
    """Mirror GNU envsubst for ${VAR} placeholders used in federation templates."""

    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        return env.get(key, os.environ.get(key, ""))

    return _ENVSUBST_PATTERN.sub(replace, text)


@pytest.mark.regression
def test_federation_toml_template_omits_ca_without_peer_ca() -> None:
    env = {
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
    rendered = envsubst_template(TEMPLATE.read_text(encoding="utf-8"), env)
    assert 'name = "crc"' in rendered
    assert "ca_cert_path" not in rendered


@pytest.mark.regression
def test_federation_toml_template_local_peer_uses_docker_dns() -> None:
    env = {
        "SDS_SITE_NAME": "crc",
        "SDS_SITE_FQDN": "sds.localhost",
        "SDS_SITE_DISPLAY_NAME": "Local CRC",
        "FEDERATION_SYNC_SERVICE_URL": "http://sds-federation-local-sync:8000/sync",
        "FEDERATION_PEER_NAME": "peer",
        "FEDERATION_PEER_FQDN": "peer.local",
        "FEDERATION_PEER_DISPLAY_NAME": "Local Peer",
        "FEDERATION_PEER_GATEWAY_API_BASE": "http://sds-gateway-local-app:8000/api/v1",
        "FEDERATION_PEER_SYNC_SERVICE_URL": "http://sds-federation-peer-sync:8000/sync",
    }
    rendered = envsubst_template(TEMPLATE.read_text(encoding="utf-8"), env)
    assert 'sync_service_url = "http://sds-federation-local-sync:8000/sync"' in rendered
    assert "sds-federation-peer-sync:8000/sync" in rendered


@pytest.mark.regression
def test_federation_toml_template_includes_registry_consumer() -> None:
    env = {
        "SDS_SITE_NAME": "fed1",
        "SDS_SITE_FQDN": "fed1.example.edu",
        "SDS_SITE_DISPLAY_NAME": "Fed1",
        "FEDERATION_SYNC_SERVICE_URL": "https://fed1.example.edu/sync",
        "FEDERATION_REGISTRY_PUBLISH_TOML": "",
        "FEDERATION_REGISTRY_CONSUMER_TOML": (
            '[registry]\nurl = "https://sds.crc.nd.edu/.well-known/sds-registry"\n'
            'public_key_path = "/etc/sds/certs/sds-registry.pub.pem"\n'
            "refresh_secs = 900\nrequired = false\n"
        ),
        "FEDERATION_PEER_NAME": "crc",
        "FEDERATION_PEER_FQDN": "sds.crc.nd.edu",
        "FEDERATION_PEER_DISPLAY_NAME": "CRC",
        "FEDERATION_PEER_GATEWAY_API_BASE": "https://sds.crc.nd.edu/api/v1",
        "FEDERATION_PEER_SYNC_SERVICE_URL": "https://sds.crc.nd.edu/sync/",
    }
    rendered = envsubst_template(TEMPLATE.read_text(encoding="utf-8"), env)
    assert "[registry]" in rendered
    assert "sds.crc.nd.edu/.well-known/sds-registry" in rendered
    assert "[registry.publish]" not in rendered


@pytest.mark.regression
def test_federation_toml_template_flagship_omits_consumer_when_publishing() -> None:
    env = {
        "SDS_SITE_NAME": "crc",
        "SDS_SITE_FQDN": "sds.crc.nd.edu",
        "SDS_SITE_DISPLAY_NAME": "CRC",
        "FEDERATION_SYNC_SERVICE_URL": "https://sds.crc.nd.edu/sync",
        "FEDERATION_REGISTRY_PUBLISH_TOML": (
            "[registry.publish]\nenabled = true\n"
            'signing_key_path = "/etc/sds/secrets/registry/sign.pem"\n'
        ),
        "FEDERATION_REGISTRY_CONSUMER_TOML": "",
        "FEDERATION_PEER_NAME": "crc",
        "FEDERATION_PEER_FQDN": "sds.crc.nd.edu",
        "FEDERATION_PEER_DISPLAY_NAME": "CRC",
        "FEDERATION_PEER_GATEWAY_API_BASE": "https://sds.crc.nd.edu/api/v1",
        "FEDERATION_PEER_SYNC_SERVICE_URL": "https://sds.crc.nd.edu/sync/",
    }
    rendered = envsubst_template(TEMPLATE.read_text(encoding="utf-8"), env)
    assert "[registry.publish]" in rendered
    assert "enabled = true" in rendered
    assert "[registry]\nurl" not in rendered.replace("[registry.publish]", "")
