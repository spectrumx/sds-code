"""User and UserAPIKey models for the Gateway."""

from typing import cast

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework_api_key.models import AbstractAPIKey

from sds_gateway.api_methods.models import KeySources

from .managers import APIKeyUserManager
from .managers import UserManager


class User(AbstractUser):
    """
    Default custom user model for SpectrumX Data System Gateway.
    If adding fields that need to be filled at user signup,
    check forms.SignupForm and forms.SocialSignupForms accordingly.
    """

    # First and last name do not cover name patterns around the globe
    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None
    name = models.CharField(_("Name of User"), blank=True, max_length=255)
    email = models.EmailField(_("Email address"), unique=True)
    is_approved = models.BooleanField(
        _("Approved"),
        default=False,
        help_text=_(
            "Designates whether this user has been approved to use the API by an Admin.",  # noqa: E501
        ),
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def get_svi_api_key(self):
        return self.svi_api_key

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"pk": self.id})


class UserAPIKey(AbstractAPIKey):
    SOURCE_CHOICES = [
        (KeySources.SDSWebUI, "SDS Web UI"),
        (KeySources.SVIBackend, "SVI Backend"),
        (KeySources.SVIWebUI, "SVI Web UI"),
    ]
    user = cast(
        "User",
        models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
    )
    source = models.CharField(
        choices=SOURCE_CHOICES,
        default=KeySources.SDSWebUI,
        max_length=255,
    )
    objects = APIKeyUserManager()
