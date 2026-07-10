"""Tests for federation sync Token + mint endpoint."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.backend_service_key_utils import mint_federation_sync_api_key
from sds_gateway.users.backend_service_key_utils import update_service_server_token
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

pytestmark = pytest.mark.django_db


class TestFederationSyncMint:
    def setup_method(self) -> None:
        email = settings.FEDERATION_SYNC_USER_EMAIL
        User.objects.filter(email=email).delete()
        update_service_server_token(
            user_email=email,
            token_key="a" * 40,
        )

    def test_mint_creates_api_key(self) -> None:
        user = User.objects.get(email=settings.FEDERATION_SYNC_USER_EMAIL)
        raw = mint_federation_sync_api_key(user)
        assert raw is not None
        key = UserAPIKey.objects.get_from_key(raw)
        assert key.source == KeySources.FederationSync
        assert key.user_id == user.pk

    def test_mint_replaces_prior_key_like_svi(self) -> None:
        user = User.objects.get(email=settings.FEDERATION_SYNC_USER_EMAIL)
        first = mint_federation_sync_api_key(user)
        second = mint_federation_sync_api_key(user)
        assert second != first
        assert (
            UserAPIKey.objects.filter(
                user=user,
                source=KeySources.FederationSync,
            ).count()
            == 1
        )


class TestGetFederationSyncApiKeyEndpoint:
    def setup_method(self) -> None:
        email = settings.FEDERATION_SYNC_USER_EMAIL
        User.objects.filter(email=email).delete()
        update_service_server_token(
            user_email=email,
            token_key="b" * 40,
        )

    def test_mint_via_http(self) -> None:
        sync_email = settings.FEDERATION_SYNC_USER_EMAIL
        sync_user = User.objects.get(email=sync_email)
        target = User.objects.create(email="mint-target@example.com", is_approved=True)
        token = Token.objects.get(user=sync_user)
        client = APIClient()
        url = reverse("users:get_federation_sync_api_key")
        response = client.get(
            f"{url}?email={target.email}",
            HTTP_AUTHORIZATION=f"Token {token.key}",
        )
        assert response.status_code == status.HTTP_200_OK
        assert "api_key" in response.json()
        assert response.json()["email"] == target.email
