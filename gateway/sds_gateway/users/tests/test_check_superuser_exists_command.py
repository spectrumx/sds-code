"""Tests for the check_superuser_exists management command."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from sds_gateway.users.models import User


@pytest.mark.django_db
def test_check_superuser_exists_outputs_no_when_none_exist() -> None:
    out = StringIO()

    command_result = call_command("check_superuser_exists", stdout=out)

    assert command_result is None
    assert out.getvalue().strip() == "no"


@pytest.mark.django_db
def test_check_superuser_exists_outputs_yes_when_one_exists() -> None:
    User.objects.create_superuser(  # pyright: ignore[reportCallIssue]
        email="existing-admin@example.com",
        password="something-r@nd0m!",  # noqa: S106
    )

    out = StringIO()

    command_result = call_command("check_superuser_exists", stdout=out)

    assert command_result is None
    assert out.getvalue().strip() == "yes"
