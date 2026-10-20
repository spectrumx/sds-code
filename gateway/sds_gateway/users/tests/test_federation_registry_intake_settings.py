from config.settings.utils import resolve_federation_registry_intake_enabled


def test_intake_disabled_when_not_requested() -> None:
    assert not resolve_federation_registry_intake_enabled(
        site_fqdn="sds.crc.nd.edu",
        flagship_gateway_host="sds.crc.nd.edu",
        intake_requested=False,
    )


def test_intake_disabled_when_site_fqdn_not_flagship() -> None:
    assert not resolve_federation_registry_intake_enabled(
        site_fqdn="peer.example.edu",
        flagship_gateway_host="sds.crc.nd.edu",
        intake_requested=True,
    )


def test_intake_enabled_only_on_flagship_host() -> None:
    assert resolve_federation_registry_intake_enabled(
        site_fqdn="sds.crc.nd.edu",
        flagship_gateway_host="sds.crc.nd.edu",
        intake_requested=True,
    )
