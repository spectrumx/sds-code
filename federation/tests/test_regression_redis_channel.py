"""Regression tests for site-prefixed federation Redis channels."""

import pytest
from sds_federation.services.redis_channel import federation_events_channel
from sds_federation.services.redis_channel import resolve_federation_events_channel


@pytest.mark.regression
def test_federation_events_channel_uses_site_name() -> None:
    assert federation_events_channel("crc") == "federation:events:crc"


def test_federation_events_channel_rejects_blank_site() -> None:
    with pytest.raises(ValueError, match="site_name"):
        federation_events_channel("  ")


def test_resolve_prefers_env_override() -> None:
    assert (
        resolve_federation_events_channel(
            site_name="crc",
            env_override="custom:channel",
        )
        == "custom:channel"
    )


def test_resolve_derives_from_site_when_no_override() -> None:
    assert (
        resolve_federation_events_channel(site_name="haystack", env_override=None)
        == "federation:events:haystack"
    )
