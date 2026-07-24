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

    def register(self, hello: SiteHelloWebhook) -> None:
        self._peers[hello.site_name] = hello

    def get(self, site_name: str) -> SiteHelloWebhook | None:
        return self._peers.get(site_name)
