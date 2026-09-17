from django.urls import resolve
from django.urls import reverse

from sds_gateway.users.models import User


def test_detail(user: User):
    assert reverse("users:detail", kwargs={"pk": user.pk}) == f"/users/{user.pk}/"
    assert resolve(f"/users/{user.pk}/").view_name == "users:detail"


def test_update():
    assert reverse("users:update") == "/users/~update/"
    assert resolve("/users/~update/").view_name == "users:update"


def test_redirect():
    assert reverse("users:redirect") == "/users/~redirect/"
    assert resolve("/users/~redirect/").view_name == "users:redirect"


def test_file_list_api_legacy_redirects_to_capture_list():
    assert reverse("users:file_list_api_legacy") == "/users/file-list/api/"
    match = resolve("/users/file-list/api/")
    assert match.view_name == "users:file_list_api_legacy"
    assert match.func.view_initkwargs["pattern_name"] == "users:capture_list"
