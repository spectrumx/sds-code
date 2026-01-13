"""Tests for the create_ci_superuser management command."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.test import override_settings

from sds_gateway.users.models import User


@pytest.mark.django_db
def test_create_ci_superuser_creates_when_none_exists() -> None:
    assert User.objects.filter(is_superuser=True).count() == 0

    command_result = call_command("create_ci_superuser")

    assert command_result is None
    assert User.objects.filter(is_superuser=True).count() == 1

    user = User.objects.get(email="admin@example.com")
    assert user.is_superuser
    assert user.is_staff
    assert user.check_password("ci-admin-pass")


@pytest.mark.django_db
def test_create_ci_superuser_skips_when_superuser_exists() -> None:
    User.objects.create_superuser(  # pyright: ignore[reportCallIssue]
        email="existing-admin@example.com",
        password="something-r@nd0m!",  # noqa: S106
    )

    assert User.objects.filter(is_superuser=True).count() == 1
    assert not User.objects.filter(email="admin@example.com").exists()

    command_result = call_command("create_ci_superuser")

    assert command_result is None
    assert User.objects.filter(is_superuser=True).count() == 1
    assert not User.objects.filter(email="admin@example.com").exists()


@pytest.mark.django_db
def test_create_ci_superuser_skips_when_django_admin_url_set() -> None:
    assert User.objects.filter(is_superuser=True).count() == 0

    with override_settings(DJANGO_ADMIN_URL="/admin/"):
        command_result = call_command("create_ci_superuser")

    assert command_result is None
    assert User.objects.filter(is_superuser=True).count() == 0
    assert not User.objects.filter(email="admin@example.com").exists()
