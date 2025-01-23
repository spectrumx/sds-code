"""User and UserAPIKey models for the Gateway."""

from typing import cast

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rest_framework_api_key.models import AbstractAPIKey
from django.db.models.signals import post_save
from django.dispatch import receiver

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
    svi_api_key = models.CharField(max_length=255, blank=True, null=True)

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


@receiver(post_save, sender=User)
def create_api_key(sender, instance, created, **kwargs):
    """Create API key for new users."""
    if created:
        api_key_obj, key = UserAPIKey.objects.create_key(
            name=f"{instance.email}-SVI-API-KEY",
            user=instance,
            source='svi_backend'
        )
        instance.svi_api_key = key
        instance.save()


class UserAPIKey(AbstractAPIKey):
    SOURCE_CHOICES = [
        ('sds_web_ui', "SDS Web UI"),
        ('sds_api', "SDS API"),
        ('svi_backend', "SVI Backend"),
    ]
    user = cast(
        User,
        models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
    )
    source = models.CharField(choices=SOURCE_CHOICES, default='sds_web_ui', max_length=255)
    objects = APIKeyUserManager()
