from __future__ import annotations

import pytest

from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_manifest import ManifestBuildError
from sds_gateway.api_methods.federation.registry_manifest import (
    build_manifest_site_list,
)
from sds_gateway.api_methods.federation.registry_manifest import manifest_min_serial
from sds_gateway.api_methods.federation.registry_manifest import (
    site_entry_from_application,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
def test_site_entry_from_application_uses_urls_and_certs(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer Site",
        contact=user,
        site_name="peer",
        gateway_api_base="https://peer.example.edu/api/v1",
        sync_service_url="https://peer.example.edu/sync",
        ca_cert_file="peer-ca.pem",
        client_cert_fingerprints=["sha256:abc"],
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.APPROVED.value,
    )
    entry = site_entry_from_application(application)
    assert entry["name"] == "peer"
    assert entry["fqdn"] == "peer.example.edu"
    assert entry["ca_cert_file"] == "peer-ca.pem"
    assert entry["client_cert_fingerprints"] == ["sha256:abc"]


@pytest.mark.django_db
def test_site_entry_defaults_urls_from_fqdn(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        site_name="peer",
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.APPROVED.value,
        verified_well_known={
            "fqdn": "peer.example.edu",
        },
    )
    entry = site_entry_from_application(application)
    assert entry["gateway_api_base"] == "https://peer.example.edu/api/v1"
    assert entry["sync_service_url"] == "https://peer.example.edu/sync"


@pytest.mark.django_db
def test_site_entry_requires_site_name(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.APPROVED.value,
    )
    with pytest.raises(ManifestBuildError, match="site id"):
        site_entry_from_application(application)


@pytest.mark.django_db
def test_build_manifest_site_list_includes_approved_and_published(user) -> None:
    RegistryApplication.objects.create(
        fqdn="a.example.edu",
        display_name="A",
        contact=user,
        site_name="site-a",
        challenge_token_hash=hash_registry_challenge_token("a"),
        status=RegistryApplicationStatus.PUBLISHED.value,
        published_manifest_serial=1,
    )
    RegistryApplication.objects.create(
        fqdn="b.example.edu",
        display_name="B",
        contact=user,
        site_name="site-b",
        challenge_token_hash=hash_registry_challenge_token("b"),
        status=RegistryApplicationStatus.APPROVED.value,
    )
    sites = build_manifest_site_list()
    assert {s["name"] for s in sites} == {"site-a", "site-b"}


@pytest.mark.django_db
def test_manifest_min_serial(user) -> None:
    assert manifest_min_serial() == 0
    RegistryApplication.objects.create(
        fqdn="a.example.edu",
        display_name="A",
        contact=user,
        site_name="site-a",
        challenge_token_hash=hash_registry_challenge_token("a"),
        status=RegistryApplicationStatus.PUBLISHED.value,
        published_manifest_serial=3,
    )
    assert manifest_min_serial() == 4
