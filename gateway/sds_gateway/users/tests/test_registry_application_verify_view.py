from __future__ import annotations

from http import HTTPStatus
from unittest.mock import patch

import pytest
from django.contrib.messages import get_messages
from django.test import override_settings
from django.urls import reverse

from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus


@pytest.mark.django_db
@override_settings(
    FEDERATION_REGISTRY_INTAKE_ENABLED=True,
    FEDERATION_SYNC_INTERNAL_URL="http://sync.test:8000",
    FEDERATION_SYNC_ADMIN_TOKEN="admin-token",
)
def test_applicant_verify_domain(client, user) -> None:
    application = RegistryApplication.objects.create(
        fqdn="site.example.edu",
        display_name="Site",
        contact=user,
        challenge_token_hash=hash_registry_challenge_token("x"),
        status=RegistryApplicationStatus.PENDING_VERIFICATION.value,
    )
    client.force_login(user)
    url = reverse(
        "users:registry_application_verify",
        kwargs={"pk": application.pk},
    )
    with patch(
        "sds_gateway.api_methods.federation.registry_application_verify.FederationSyncClient.from_settings",
    ) as mock_factory:
        mock_client = mock_factory.return_value
        mock_client.verify_domain.return_value = {
            "ok": True,
            "well_known": {
                "fqdn": "site.example.edu",
                "gateway_api_base": "https://site.example.edu/api/v1",
                "sync_service_url": "https://site.example.edu/sync",
            },
        }
        response = client.post(url)
    assert response.status_code == HTTPStatus.FOUND
    application.refresh_from_db()
    assert application.status == RegistryApplicationStatus.PENDING_APPROVAL.value
    flash = [str(m) for m in get_messages(response.wsgi_request)]
    assert any("awaiting" in m.lower() for m in flash)
