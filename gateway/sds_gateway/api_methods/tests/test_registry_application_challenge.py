from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone

from sds_gateway.api_methods.federation.registry_application_challenge import (
    reissue_registry_challenge,
)
from sds_gateway.api_methods.federation.registry_application_challenge import (
    withdraw_registry_application,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus
from sds_gateway.api_methods.models import fqdn_has_open_registry_application
from sds_gateway.users.forms import RegistryApplicationForm


@pytest.mark.django_db
def test_withdraw_releases_fqdn(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="release.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash="abc",
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    assert fqdn_has_open_registry_application("release.example.edu")

    result = withdraw_registry_application(application)
    assert result.ok
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.WITHDRAWN.value
    assert not fqdn_has_open_registry_application("release.example.edu")

    form = RegistryApplicationForm(
        data={
            "fqdn": "release.example.edu",
            "display_name": "Again",
            "proposed_site_name": "again",
        },
    )
    assert form.is_valid()


@pytest.mark.django_db
def test_reissue_rotates_challenge(user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("old"),
        status=RegistryApplicationStatus.VERIFICATION_FAILED.value,
        challenge_expires_at=timezone.now() - timezone.timedelta(hours=1),
        last_verification_error="failed",
    )
    old_hash = application.challenge_token_hash

    result = reissue_registry_challenge(application)
    assert result.ok
    assert result.raw_token

    application.refresh_from_db()
    assert application.challenge_token_hash != old_hash
    assert application.challenge_expires_at > timezone.now()
    assert application.status == RegistryApplicationStatus.PENDING_VERIFICATION.value
    assert application.last_verification_error == ""


@pytest.mark.django_db
def test_applicant_can_reissue_via_post(client, user, settings) -> None:
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = True
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash="abc",
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    client.force_login(user)
    url = reverse(
        "users:registry_application_reissue_challenge",
        kwargs={"pk": application.pk},
    )
    response = client.post(url)
    assert response.status_code == 302
    application.refresh_from_db()
    assert application.challenge_token_hash != "abc"
