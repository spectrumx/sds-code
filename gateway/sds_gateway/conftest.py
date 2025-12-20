# ruff: noqa: E402

import os
from pathlib import Path

import django
import pytest

# set DJANGO_SETTINGS_MODULE only if it's not already set, to access the models
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

# without calling setup we get the "apps aren't loaded yet" error
django.setup()

# now we can import the models and settings
from django.conf import settings

from sds_gateway.users.models import User
from sds_gateway.users.tests.factories import UserFactory


@pytest.fixture(autouse=True)
def _media_storage(settings, tmpdir) -> None:
    settings.MEDIA_ROOT = tmpdir.strpath


@pytest.fixture
def user(db) -> User:
    return UserFactory()


def pytest_collection_modifyitems(config, items):
    """Deselect visualization tests entirely if feature is disabled."""
    if settings.VISUALIZATIONS_ENABLED:
        return

    # Remove visualization tests from collection
    deselected = []
    remaining = []

    for item in items:
        # Check if test is in visualizations module
        item_path = Path(str(item.fspath))
        if "visualizations" in item_path.parts and "tests" in item_path.parts:
            deselected.append(item)
        else:
            remaining.append(item)

    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining
