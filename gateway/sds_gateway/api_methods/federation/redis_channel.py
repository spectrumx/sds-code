"""Redis pub/sub channel naming for federation change events (RFC §8)."""

from __future__ import annotations


def resolve_federation_events_channel(
    *,
    site_name: str = "",
    channel_override: str = "",
) -> str:
    """Return the Redis channel for local federation events.

    Override ``channel_override`` when set (``FEDERATION_EVENTS_CHANNEL`` env).
    Otherwise use ``federation:events:{site_name}`` when ``site_name`` is set.
    """
    override = (channel_override or "").strip()
    if override:
        return override
    site = (site_name or "").strip()
    if site:
        return f"federation:events:{site}"
    return ""
