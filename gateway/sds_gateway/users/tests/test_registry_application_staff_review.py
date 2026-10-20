from __future__ import annotations

import pytest
from django.urls import reverse

from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
def test_staff_can_approve_from_detail_post(client, user, settings) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = True
    applicant = user
    staff = user.__class__.objects.create_user(
        email="staff@example.com",
        password="test-pass-12345",
        is_staff=True,
    )
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=applicant,
        proposed_site_name="mysite",
        challenge_token_hash="hash",
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )

    client.force_login(staff)
    url = reverse("users:registry_application_approve", kwargs={"pk": application.pk})
    response = client.post(url, {"site_name": "mysite"})

    assert response.status_code == 302
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.APPROVED.value
    assert application.site_name == "mysite"
    assert application.reviewed_by_id == staff.pk


@pytest.mark.django_db
def test_non_staff_cannot_approve(client, user, settings) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = True
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        proposed_site_name="mysite",
        challenge_token_hash="hash",
        status=RegistryApplicationStatus.PENDING_APPROVAL.value,
    )

    client.force_login(user)
    url = reverse("users:registry_application_approve", kwargs={"pk": application.pk})
    response = client.post(url, {"site_name": "mysite"})

    assert response.status_code == 403
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value
