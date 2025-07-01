"""Test utilities for SVI server token management."""

import pytest
from django.conf import settings
from django.db.utils import IntegrityError
from rest_framework.authtoken.models import Token

from sds_gateway.users.models import User
from sds_gateway.users.svi_utils import update_svi_server_token


@pytest.mark.django_db
class TestSVITokenUpdate:
    """Test SVI server token update functionality."""

    def setup_method(self) -> None:
        """Clean up any existing SVI server user and tokens."""
        User.objects.filter(email=settings.SVI_SERVER_EMAIL).delete()

    def test_creates_user_and_token(self) -> None:
        """Test that update_svi_server_token creates user and token."""
        # ensure no user exists initially
        assert not User.objects.filter(email=settings.SVI_SERVER_EMAIL).exists()

        # run the update function
        update_svi_server_token()

        # verify user was created
        user = User.objects.get(email=settings.SVI_SERVER_EMAIL)
        assert user.is_active
        assert user.is_approved

        # verify token was created with correct key
        token = Token.objects.get(user=user)
        assert token.key == settings.SVI_SERVER_API_KEY

    def test_updates_existing_token(self) -> None:
        """Test that update_svi_server_token updates existing token."""
        # ARRANGE: create user and old token
        user = User.objects.create_user(  # pyright: ignore[reportCallIssue]
            email=settings.SVI_SERVER_EMAIL,
            is_active=True,
            is_approved=True,
        )
        old_token_key = "old-token-key"  # noqa: S105
        assert old_token_key != settings.SVI_SERVER_API_KEY, "Failed precondition check"
        old_token = Token.objects.create(user=user, key=old_token_key)

        # ACT: run the update function
        update_svi_server_token()

        # ASSERT: old token is removed, new token is created with correct key
        assert not Token.objects.filter(pk=old_token.pk).exists()
        new_token = Token.objects.get(user=user)
        assert new_token.key == settings.SVI_SERVER_API_KEY
        assert new_token.key != old_token_key

    def test_multiple_tokens_forbidden(self) -> None:
        """Test that multiple tokens for SVI server user are not allowed."""
        # ARRANGE: create user with a token
        user = User.objects.create_user(  # pyright: ignore[reportCallIssue]
            email=settings.SVI_SERVER_EMAIL,
            is_active=True,
            is_approved=True,
        )

        Token.objects.create(user=user, key="token1")

        # ACT/ASSERT: try to create a second token for the same user

        with pytest.raises(expected_exception=IntegrityError):
            Token.objects.create(user=user, key="token2")
