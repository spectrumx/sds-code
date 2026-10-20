from __future__ import annotations

import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_registry_list_404_when_intake_disabled(client, user, settings) -> None:
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = False
    client.force_login(user)

    response = client.get(reverse("users:registry_application_list"))

    assert response.status_code == 404


@pytest.mark.django_db
def test_registry_list_ok_when_intake_enabled(client, user, settings) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FLAGSHIP_GATEWAY_HOST = "sds.crc.nd.edu"
    settings.FEDERATION_REGISTRY_INTAKE_ENABLED = True
    client.force_login(user)

    response = client.get(reverse("users:registry_application_list"))

    assert response.status_code == 200
