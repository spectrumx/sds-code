"""Redis pub/sub channel naming for federation local change events."""

from __future__ import annotations

FEDERATION_EVENTS_CHANNEL_PREFIX = "federation:events"


def federation_events_channel(site_name: str) -> str:
    """Site-scoped channel."""
    name = site_name.strip()
    if not name:
        msg = "site_name is required to build a federation events channel"
        raise ValueError(msg)
    return f"{FEDERATION_EVENTS_CHANNEL_PREFIX}:{name}"


def resolve_federation_events_channel(
    *,
    site_name: str,
    env_override: str | None = None,
) -> str:
    """Channel for subscribe/publish; env override wins when set."""
    if env_override is not None and env_override.strip():
        return env_override.strip()
    return federation_events_channel(site_name)
