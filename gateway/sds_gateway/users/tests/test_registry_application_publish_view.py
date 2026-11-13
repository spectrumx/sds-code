from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.urls import reverse

from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.federation.registry_application_staff_ops import (
    StaffOpResult,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
def test_staff_publish_registry_post(client, user, settings) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = True
    staff = user.__class__.objects.create_user(
        email="staff@example.com",
        password="test-pass-12345",
        is_staff=True,
    )
    RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        site_name="peer",
        gateway_api_base="https://peer.example.edu/api/v1",
        sync_service_url="https://peer.example.edu/sync",
        challenge_token_hash=hash_registry_challenge_token("p"),
        status=RegistryApplicationStatus.APPROVED.value,
    )

    client.force_login(staff)
    url = reverse("users:registry_application_publish_manifest")
    with (
        patch(
            "sds_gateway.users.views.registry_application.registry_sync_publish_enabled",
            return_value=True,
        ),
        patch(
            "sds_gateway.users.views.registry_application.publish_registry_manifest",
            return_value=StaffOpResult(
                ok=True,
                message="Published registry manifest serial 2 (peer).",
                serial=2,
                site_names=("peer",),
            ),
        ),
    ):
        response = client.post(url)

    assert response.status_code == HTTPStatus.FOUND
    assert response.url == reverse("users:registry_application_list")


@pytest.mark.django_db
def test_non_staff_cannot_publish(client, user, settings) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = True
    client.force_login(user)
    url = reverse("users:registry_application_publish_manifest")
    response = client.post(url)
    assert response.status_code == HTTPStatus.FORBIDDEN
