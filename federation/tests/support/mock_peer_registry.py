from __future__ import annotations

from sds_federation.schemas.webhooks import SiteHelloWebhook
from sds_federation.services.peer_registry import PeerRegistry


class RecordingPeerRegistry(PeerRegistry):
    """PeerRegistry that records every site-hello for test assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.registration_events: list[SiteHelloWebhook] = []

    def register(self, hello: SiteHelloWebhook) -> None:
        self.registration_events.append(hello)
        super().register(hello)
