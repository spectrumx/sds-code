from __future__ import annotations

import pytest

from sds_gateway.api_methods.federation.registry_application_review import (
    approve_registry_application,
)
from sds_gateway.api_methods.federation.registry_application_review import (
    reject_registry_application,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
def test_approve_registry_application_success(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        proposed_site_name="mysite",
        challenge_token_hash="abc",
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
        verified_well_known={
            "gateway_api_base": "https://site.example.edu/api/v1",
            "sync_service_url": "https://site.example.edu/sync/",
        },
    )
    staff = user
    staff.is_staff = True
    staff.save(update_fields=["is_staff"])

    result = approve_registry_application(application, staff)

    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.APPROVED.value
    assert application.site_name == "mysite"
    assert application.reviewed_by == staff
    assert application.reviewed_at is not None
    assert application.gateway_api_base == "https://site.example.edu/api/v1"


@pytest.mark.django_db
def test_approve_registry_application_rejects_duplicate_site_name(user) -> None:
    RegistryApplication.objects.create(
        fqdn="existing.example.edu",
        display_name="Existing",
        contact=user,
        site_name="taken",
        challenge_token_hash="x",
        status=RegistryApplicationStatus.APPROVED.value,
    )
    application = RegistryApplication.objects.create(
        fqdn="new.example.edu",
        display_name="New",
        contact=user,
        proposed_site_name="taken",
        challenge_token_hash="y",
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )

    result = approve_registry_application(application, user)

    assert not result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value


@pytest.mark.django_db
def test_reject_registry_application(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash="abc",
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )

    result = reject_registry_application(application, user, reason="Not ready")

    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.REJECTED.value
    assert application.rejected_reason == "Not ready"
