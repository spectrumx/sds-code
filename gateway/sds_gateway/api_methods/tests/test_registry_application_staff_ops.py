from __future__ import annotations

from unittest.mock import patch

import pytest
from django.core.cache import cache

from sds_gateway.api_methods.federation.registry_application_staff_ops import (
    publish_registry_manifest,
)
from sds_gateway.api_methods.federation.registry_challenge import (
    hash_registry_challenge_token,
)
from sds_gateway.api_methods.federation.sync_client import SyncUnavailableError
from sds_gateway.api_methods.models import RegistryApplication
from sds_gateway.api_methods.models import RegistryApplicationStatus

_MANIFEST_SERIAL = 5


@pytest.mark.django_db
def test_publish_registry_manifest_marks_approved_published(user, settings) -> None:
    settings.FEDERATION_SYNC_INTERNAL_URL = "http://sync.test:8000"
    settings.FEDERATION_SYNC_ADMIN_TOKEN = "token"
    cache.clear()

    published = RegistryApplication.objects.create(
        fqdn="old.example.edu",
        display_name="Old",
        contact=user,
        site_name="old",
        gateway_api_base="https://old.example.edu/api/v1",
        sync_service_url="https://old.example.edu/sync",
        challenge_token_hash=hash_registry_challenge_token("o"),
        status=RegistryApplicationStatus.PUBLISHED.value,
        published_manifest_serial=2,
    )
    approved = RegistryApplication.objects.create(
        fqdn="peer.example.edu",
        display_name="Peer",
        contact=user,
        site_name="peer",
        gateway_api_base="https://peer.example.edu/api/v1",
        sync_service_url="https://peer.example.edu/sync",
        challenge_token_hash=hash_registry_challenge_token("p"),
        status=RegistryApplicationStatus.APPROVED.value,
    )

    with (
        patch(
            "sds_gateway.api_methods.federation.registry_application_staff_ops."
            "FederationSyncClient.from_settings"
        ) as mock_from_settings,
        patch(
            "sds_gateway.api_methods.federation.registry_application_staff_ops."
            "registry_sync_publish_enabled",
            return_value=True,
        ),
    ):
        client = mock_from_settings.return_value
        client.publish.return_value = {
            "serial": _MANIFEST_SERIAL,
            "site_names": ["crc", "old", "peer"],
        }
        result = publish_registry_manifest()

    assert result.ok
    assert result.serial == _MANIFEST_SERIAL
    approved.refresh_from_db()
    published.refresh_from_db()
    assert approved.status == RegistryApplicationStatus.PUBLISHED.value
    assert approved.published_manifest_serial == _MANIFEST_SERIAL
    assert published.published_manifest_serial == _MANIFEST_SERIAL
    call = client.publish.call_args
    assert call.kwargs["min_serial"] == 3
    sites = call.args[0]
    assert {s["name"] for s in sites} == {"old", "peer"}


@pytest.mark.django_db
def test_publish_registry_manifest_skips_pending(user) -> None:
    with (
        patch(
            "sds_gateway.api_methods.federation.registry_application_staff_ops."
            "registry_sync_publish_enabled",
            return_value=True,
        ),
        patch(
            "sds_gateway.api_methods.federation.registry_application_staff_ops."
            "FederationSyncClient.from_settings",
        ),
    ):
        result = publish_registry_manifest()
    assert not result.ok
    assert "Approve" in result.message


@pytest.mark.django_db
def test_publish_registry_manifest_sync_unavailable(user) -> None:
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
    with (
        patch(
            "sds_gateway.api_methods.federation.registry_application_staff_ops."
            "registry_sync_publish_enabled",
            return_value=True,
        ),
        patch(
            "sds_gateway.api_methods.federation.registry_application_staff_ops."
            "FederationSyncClient.from_settings"
        ) as mock_from_settings,
    ):
        mock_from_settings.return_value.publish.side_effect = SyncUnavailableError(
            "down"
        )
        result = publish_registry_manifest()
    assert not result.ok
