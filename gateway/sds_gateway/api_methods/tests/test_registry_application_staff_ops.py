from __future__ import annotations

import pytest

from sds_gateway.api_methods.federation.registry_application_staff_ops import (
    record_manifest_published,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_MANIFEST_SERIAL = 2


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
    result = record_manifest_published(serial=_MANIFEST_SERIAL)
    assert result.ok
    app = RegistryApplication.objects.get(site_name="peer")
    assert app.status == RegistryApplicationStatus.PUBLISHED.value
    assert app.published_manifest_serial == _MANIFEST_SERIAL
