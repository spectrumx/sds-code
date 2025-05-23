from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _
from rest_framework_api_key.models import APIKey

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User
from .models import UserAPIKey

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]

# unregister the existing APIKey model only if it is registered
if APIKey in admin.site._registry:  # noqa: SLF001
    admin.site.unregister(APIKey)


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):  # pyright: ignore[reportMissingTypeArgument]
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (_("Personal info"), {"fields": ("name",)}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_approved",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = ["email", "name", "is_superuser"]
    search_fields = ["name"]
    ordering = ["id"]
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )


@admin.register(UserAPIKey)
class APIKeyAdmin(admin.ModelAdmin):  # pyright: ignore[reportMissingTypeArgument]
    list_display = [
        "prefix",
        "name",
        "user",
        "created",
        "expiry_date",
        "_has_expired",
        "revoked",
    ]
    search_fields = ["user__email"]
    ordering = ["-created"]
    date_hierarchy = "created"
