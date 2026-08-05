"""Shared Redis pub/sub channel naming for federation local change events."""

from __future__ import annotations

FEDERATION_EVENTS_CHANNEL_PREFIX = "federation:events"


def federation_events_channel(site_name: str) -> str:
    """Site-scoped channel ``federation:events:{site_name}``."""
    name = site_name.strip()
    if not name:
        msg = "site_name is required to build a federation events channel"
        raise ValueError(msg)
    return f"{FEDERATION_EVENTS_CHANNEL_PREFIX}:{name}"


def resolve_federation_events_channel(
    *,
    site_name: str = "",
    channel_override: str | None = None,
    env_override: str | None = None,
    gateway_site_name: str | None = None,
) -> str:
    """Resolve the Redis channel for local federation events.

    Precedence:
    1. ``channel_override`` / ``env_override`` (``FEDERATION_EVENTS_CHANNEL``) when set
    2. ``gateway_site_name`` (``FEDERATION_SITE_NAME``) when set
       — matches gateway publish
    3. ``site_name`` (e.g. federation.toml ``[site].name``) when set
    4. empty string when nothing is configured (gateway settings default)
    """
    override = (
        channel_override if channel_override is not None else env_override
    ) or ""
    if override.strip():
        return override.strip()
    gateway = (gateway_site_name or "").strip()
    if gateway:
        return federation_events_channel(gateway)
    site = (site_name or "").strip()
    if site:
        return federation_events_channel(site)
    return ""
