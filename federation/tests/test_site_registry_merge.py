from __future__ import annotations

from datetime import UTC
from datetime import datetime
from datetime import timedelta

from sds_federation.models import FederationConfig
from sds_federation.models import PeerInfo
from sds_federation.models import SiteInfo
from sds_federation.schemas.registry import RegistryManifest
from sds_federation.schemas.registry import RegistrySite
from sds_federation.schemas.registry import SiteStatusEnum
from sds_federation.services.site_registry import apply_peers
from sds_federation.services.site_registry import merge_peers


def _config(*, peers: list[PeerInfo] | None = None) -> FederationConfig:
    return FederationConfig(
        site=SiteInfo(name="local", fqdn="local.test", display_name="Local"),
        peers=peers or [],
        gateway_api_base="http://local.test/api/v1",
        sync_service_url="http://local.test/sync",
    )


def _manifest(*sites: RegistrySite) -> RegistryManifest:
    now = datetime.now(UTC)
    return RegistryManifest(
        schema_version=1,
        serial=1,
        issued_at=now,
        expires_at=now + timedelta(days=7),
        sites=list(sites),
    )


def _registry_site(
    name: str,
    fqdn: str,
    *,
    status: SiteStatusEnum = SiteStatusEnum.ACTIVE,
) -> RegistrySite:
    return RegistrySite(
        name=name,
        fqdn=fqdn,
        display_name=name,
        status=status,
        gateway_api_base=f"https://{fqdn}/api/v1",
        sync_service_url=f"https://{fqdn}/sync",
    )


def test_merge_drops_registry_peer_after_removal_from_manifest() -> None:
    static = PeerInfo(
        name="pinned",
        fqdn="pinned.test",
        display_name="Pinned",
        gateway_api_base="http://pinned.test/api/v1",
        sync_service_url="http://pinned.test/sync",
    )
    config = _config(peers=[static])
    first = merge_peers(
        config,
        _manifest(_registry_site("fed", "fed.test")),
    )
    assert {p.fqdn for p in first} == {"pinned.test", "fed.test"}

    config.peers[:] = first
    second = merge_peers(config, _manifest())
    assert {p.fqdn for p in second} == {"pinned.test"}


async def test_apply_peers_then_merge_drops_retired_registry_site() -> None:
    config = _config()
    with_registry = merge_peers(
        config,
        _manifest(_registry_site("fed", "fed.test")),
    )
    await apply_peers(config, with_registry)
    assert {p.fqdn for p in config.peers} == {"fed.test"}

    without_registry = merge_peers(config, _manifest())
    await apply_peers(config, without_registry)
    assert config.peers == []


def test_static_pin_wins_over_registry_urls() -> None:
    static = PeerInfo(
        name="peer",
        fqdn="peer.test",
        display_name="Pinned",
        gateway_api_base="http://custom/api/v1",
        sync_service_url="http://custom/sync",
    )
    config = _config(peers=[static])
    merged = merge_peers(
        config,
        _manifest(
            _registry_site("peer", "peer.test"),
        ),
    )
    peer = next(p for p in merged if p.fqdn == "peer.test")
    assert str(peer.gateway_api_base) == "http://custom/api/v1"


def test_registry_peer_urls_update_when_not_pinned() -> None:
    config = _config()
    first = merge_peers(
        config,
        _manifest(
            RegistrySite(
                name="fed",
                fqdn="fed.test",
                display_name="Fed",
                gateway_api_base="https://fed.test/api/v1",
                sync_service_url="https://fed.test/sync",
            ),
        ),
    )
    second = merge_peers(
        config,
        _manifest(
            RegistrySite(
                name="fed",
                fqdn="fed.test",
                display_name="Fed",
                gateway_api_base="https://fed.test/api/v2",
                sync_service_url="https://fed.test/sync/v2",
            ),
        ),
    )
    assert str(first[0].gateway_api_base).endswith("/api/v1")
    assert str(second[0].gateway_api_base).endswith("/api/v2")
