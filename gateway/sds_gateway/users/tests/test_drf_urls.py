from django.conf import settings
from django.urls import resolve
from django.urls import reverse

from sds_gateway.users.models import User

API_VERSION = settings.API_VERSION


def test_user_detail(user: User) -> None:
    user_detail_url = f"/api/{API_VERSION}/users/{user.pk}/"
    assert reverse("api:user-detail", kwargs={"pk": user.pk}) == user_detail_url
    assert resolve(user_detail_url).view_name == "api:user-detail"


def test_user_list() -> None:
    assert reverse("api:user-list") == f"/api/{API_VERSION}/users/"
    assert resolve(f"/api/{API_VERSION}/users/").view_name == "api:user-list"


def test_user_me() -> None:
    assert reverse("api:user-me") == f"/api/{API_VERSION}/users/me/"
    assert resolve(f"/api/{API_VERSION}/users/me/").view_name == "api:user-me"
