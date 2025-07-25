import contextlib

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class UsersConfig(AppConfig):
    name = "sds_gateway.users"
    verbose_name = _("Users")

    def ready(self) -> None:
        with contextlib.suppress(ImportError):
            import sds_gateway.users.signals  # pyright: ignore[reportMissingImports]  # noqa: F401
