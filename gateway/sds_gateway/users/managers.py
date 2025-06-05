from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import UserManager as DjangoUserManager
from rest_framework_api_key.models import APIKeyManager

if TYPE_CHECKING:
    from .models import User


class UserManager(DjangoUserManager["User"]):
    """Custom manager for the User model."""

    def _create_user(
        self,
        email: str,
        password: str | None,
        **extra_fields,
    ) -> "User":
        """
        Create and save a user with the given email and password.
        """
        if not email:
            msg = "The given email must be set"
            raise ValueError(msg)
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_user(  # type: ignore[reportIncompatibleMethodOverride]
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":  # type: ignore[override]
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        extra_fields.setdefault(
            "is_approved", settings.SDS_NEW_USERS_APPROVED_ON_CREATION
        )
        return self._create_user(email=email, password=password, **extra_fields)

    def create_superuser(  # type: ignore[reportIncompatibleMethodOverride]
        self,
        email: str,
        password: str | None = None,
        **extra_fields,
    ) -> "User":
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            msg = "Superuser must have is_staff=True."
            raise ValueError(msg)
        if extra_fields.get("is_superuser") is not True:
            msg = "Superuser must have is_superuser=True."
            raise ValueError(msg)

        return self._create_user(email=email, password=password, **extra_fields)


class APIKeyUserManager(APIKeyManager):
    """Custom manager for the APIKey model."""

    def get_from_user(self, user):
        try:
            return self.get(user=user)
        except self.model.DoesNotExist:
            return None
