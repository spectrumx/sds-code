# ruff: noqa: E402

import os

import django
import pytest

# set DJANGO_SETTINGS_MODULE only if it's not already set, to access the models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# without calling setup we get the "apps aren't loaded yet" error
django.setup()

# now we can import the models
from sds_gateway.users.models import User
from sds_gateway.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()
