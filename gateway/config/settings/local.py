"""Setting overrides for local development."""
# ruff: noqa: F405

import django_stubs_ext

from .base import *  # noqa: F403 pylint: disable=wildcard-import,unused-wildcard-import
from .base import INSTALLED_APPS
from .base import MIDDLEWARE
from .base import WEBPACK_LOADER
from .base import env

# Better type hinting for Django models
# https://github.com/sbdchd/django-types
django_stubs_ext.monkeypatch()

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/4.2/ref/settings/#debug
DEBUG: bool = True
# https://docs.djangoproject.com/en/4.2/ref/settings/#secret-key
SECRET_KEY: str = env(
    "DJANGO_SECRET_KEY",
    default="7SGPiDXuHen3CinEGQ4GjOnzHVgcS28Mpbf6zTuHWJtELgpo1FyWs25IeaCR5Sfn",
)
# https://docs.djangoproject.com/en/4.2/ref/settings/#allowed-hosts
ALLOWED_HOSTS: list[str] = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=[
        "localhost",
        "0.0.0.0",
        "127.0.0.1",
        "sds-gateway-local-app",  # internal docker name
        "sds-dev.crc.nd.edu",  # to test with traefik; change your /etc/hosts file
    ],
)

# CACHES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/4.2/ref/settings/#caches
CACHES: dict[str, Any] = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    },
}

# EMAIL
# ------------------------------------------------------------------------------

# MailHog SMTP settings for local development
DEFAULT_FROM_EMAIL: str = "noreply@spectrumx.local"

# WHITENOISE
# ------------------------------------------------------------------------------
# http://whitenoise.evans.io/en/latest/django.html#using-whitenoise-in-development
INSTALLED_APPS: list[str] = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]


# DJANGO-DEBUG-TOOLBAR
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS.extend(["debug_toolbar"])
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE.extend(["debug_toolbar.middleware.DebugToolbarMiddleware"])
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG: dict[str, Any] = {
    "DISABLE_PANELS": [
        "debug_toolbar.panels.redirects.RedirectsPanel",
        # Disable profiling panel due to an issue with Python 3.12:
        # https://github.com/jazzband/django-debug-toolbar/issues/1875
        "debug_toolbar.panels.profiling.ProfilingPanel",
    ],
    "SHOW_TEMPLATE_CONTEXT": True,
}
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips
INTERNAL_IPS: list[str] = ["127.0.0.1", "10.0.2.2"]
if env("USE_DOCKER") == "yes":
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS.extend([".".join([*ip.split(".")[:-1], "1"]) for ip in ips])
    try:
        _, _, ips = socket.gethostbyname_ex("node")
        INTERNAL_IPS.extend(ips)
    except socket.gaierror:
        # The node container isn't started (yet?)
        pass

# SENTRY
# ------------------------------------------------------------------------------
# https://docs.sentry.io/platforms/python/guides/django/
SENTRY_DSN: str = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment="local",
        # whether to add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/
        send_default_pii=False,
    )

# CELERY
# ------------------------------------------------------------------------------

# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-eager-propagates
# CELERY_TASK_EAGER_PROPAGATES: bool = True  # noqa: ERA001
# django-webpack-loader
# ------------------------------------------------------------------------------
WEBPACK_LOADER["DEFAULT"]["CACHE"] = not DEBUG
# ------------------------------------------------------------------------------

# BUSINESS LOGIC
# ------------------------------------------------------------------------------
# Whether new users are approved to generate API keys on creation or not.
SDS_NEW_USERS_APPROVED_ON_CREATION: bool = env.bool(
    "SDS_NEW_USERS_APPROVED_ON_CREATION",
    default=True,
)
