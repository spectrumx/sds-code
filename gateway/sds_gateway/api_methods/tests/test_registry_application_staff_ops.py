from __future__ import annotations

import pytest

from sds_gateway.api_methods.federation.registry_application_staff_ops import (
    mark_domain_verified,
)
from sds_gateway.api_methods.federation.registry_application_staff_ops import (
    record_manifest_published,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
def test_mark_domain_verified(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("t"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    result = mark_domain_verified(application)
    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value


@pytest.mark.django_db
def test_record_manifest_published(user) -> None:
    RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        site_name="peer",
        challenge_token_hash=hash_registry_challenge_token("p"),
        status=RegistryApplicationStatus.APPROVED.value,
    )
    result = record_manifest_published(serial=2)
    assert result.ok
    app = RegistryApplication.objects.get(site_name="peer")
    assert app.status == RegistryApplicationStatus.PUBLISHED.value
    assert app.published_manifest_serial == 2
