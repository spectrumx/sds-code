"""In-memory registry of peers that completed site-hello."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sds_federation.schemas.webhooks import SiteHelloWebhook


class PeerRegistry:
    def __init__(self) -> None:
        self._peers: dict[str, SiteHelloWebhook] = {}
        self._last_seen: dict[str, datetime] = {}

    def register(self, hello: SiteHelloWebhook) -> None:
        self._peers[hello.site_name] = hello
        self._last_seen[hello.site_name] = datetime.now(UTC)

    def get(self, site_name: str) -> SiteHelloWebhook | None:
        return self._peers.get(site_name)

    def known_site_names(self) -> set[str]:
        return set(self._peers.keys())
