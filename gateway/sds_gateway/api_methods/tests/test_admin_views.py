"""Smoke tests for api_methods admin views.

Loads each registered admin changelist view to catch import errors and
attribute mistakes (e.g. using ``models.PositiveIntegerField()`` instead of
``from django.db.models import PositiveIntegerField``).  The changelist view
is the most complex — it triggers ``get_queryset``, custom annotations, and
``list_display`` methods.
"""

from http import HTTPStatus

import pytest
from django.test.client import Client
from django.urls import reverse

from sds_gateway.users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

# All admin models registered in api_methods.admin.
ADMIN_CHANGELIST_URL_NAMES: list[str] = [
    "admin:api_methods_file_changelist",
    "admin:api_methods_capture_changelist",
    "admin:api_methods_dataset_changelist",
    "admin:api_methods_temporaryzipfile_changelist",
    "admin:api_methods_usersharepermission_changelist",
    "admin:api_methods_deprecatedpostprocesseddata_changelist",
    "admin:api_methods_sharegroup_changelist",
    "admin:api_methods_keyword_changelist",
]


@pytest.fixture
def admin_user():
    return UserFactory(is_staff=True, is_superuser=True)


@pytest.mark.parametrize(
    "url_name",
    ADMIN_CHANGELIST_URL_NAMES,
    ids=[
        "FileAdmin",
        "CaptureAdmin",
        "DatasetAdmin",
        "TemporaryZipFileAdmin",
        "UserSharePermissionAdmin",
        "PostProcessedDataAdmin",
        "ShareGroupAdmin",
        "KeywordAdmin",
    ],
)
def test_admin_changelist_loads(url_name: str, admin_user, client: Client) -> None:
    """Each admin changelist view must return 200 without import/type errors."""
    client.force_login(admin_user)
    response = client.get(reverse(url_name))
    assert response.status_code == HTTPStatus.OK
