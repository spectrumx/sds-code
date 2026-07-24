"""Regression tests for peer outbound URL overlay."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime

import pytest
from sds_federation.models import PeerInfo
from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.services.peer_registry import PeerRegistry
from sds_federation.services.peer_sync import peer_for_outbound
from sds_federation.services.peer_sync import peer_webhook_url


@pytest.mark.regression
def test_peer_for_outbound_falls_back_to_toml_without_registry() -> None:
    peer = PeerInfo(
        name="peer-one",
        fqdn="peer.test",
        display_name="Peer",
        gateway_api_base="http://peer-gateway.test/api/v1",
        sync_service_url="http://toml-sync.test/sync",
    )
    assert peer_for_outbound(peer, None) is peer
    assert peer_for_outbound(peer, PeerRegistry()) is peer


@pytest.mark.regression
def test_peer_for_outbound_overlays_site_hello_url() -> None:
    peer = PeerInfo(
        name="peer-one",
        fqdn="peer.test",
        display_name="Peer",
        gateway_api_base="http://peer-gateway.test/api/v1",
        sync_service_url="http://toml-sync.test/sync",
        ca_cert_path="/etc/sds/certs/peer.pem",
    )
    registry = PeerRegistry()
    registry.register(
        SiteHelloWebhook(
            site_name="peer-one",
            fqdn="peer.test",
            display_name="Peer",
            sync_service_url="http://live-sync.test/sync",
            timestamp=datetime.now(UTC),
        ),
    )
    outbound = peer_for_outbound(peer, registry)
    assert str(outbound.sync_service_url).rstrip("/") == "http://live-sync.test/sync"
    assert outbound.ca_cert_path == peer.ca_cert_path
    assert peer_webhook_url(outbound, "/webhook/dataset-updated") == (
        "http://live-sync.test/sync/api/v1/webhook/dataset-updated"
    )
