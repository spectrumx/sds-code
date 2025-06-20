"""⚠️ Setting overrides for PRODUCTION ⚠️"""
# ruff: noqa: F405, ERA001

from socket import gethostname

from .base import *  # noqa: F403 pylint: disable=wildcard-import,unused-wildcard-import
from .base import DATABASES
from .base import SPECTACULAR_SETTINGS
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
# DEBUG: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY: str = env("DJANGO_SECRET_KEY")
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS: list[str] = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=[
        "sds-gateway-prod-app",  # internal docker name
        "sds.crc.nd.edu",
    ],
)

# DATABASES
# ------------------------------------------------------------------------------
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=60)

# CACHES
# ------------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # Mimicing memcache behavior.
            # https://github.com/jazzband/django-redis#memcached-exceptions-behavior
            "IGNORE_EXCEPTIONS": True,
        },
    },
}

# ⚠️ Setting overrides for PRODUCTION

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-proxy-ssl-header
SECURE_PROXY_SSL_HEADER: tuple[str, ...] = ("HTTP_X_FORWARDED_PROTO", "https")
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-ssl-redirect
SECURE_SSL_REDIRECT: bool = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-secure
SESSION_COOKIE_SECURE: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-name
SESSION_COOKIE_NAME: str = "__Secure-sessionid"
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-secure
CSRF_COOKIE_SECURE: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-name
CSRF_COOKIE_NAME: str = "__Secure-csrftoken"
# https://docs.djangoproject.com/en/dev/topics/security/#ssl-https
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-seconds
# TODO: set this to 60 seconds first and then to 518400 once you prove the former works
# !!! Setting this incorrectly can irreversibly (for some time) break your site !!!
SECURE_HSTS_SECONDS: int = 60
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-include-subdomains
SECURE_HSTS_INCLUDE_SUBDOMAINS: bool = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
)
# https://docs.djangoproject.com/en/dev/ref/settings/#secure-hsts-preload
SECURE_HSTS_PRELOAD: bool = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
# https://docs.djangoproject.com/en/dev/ref/middleware/#x-content-type-options-nosniff
SECURE_CONTENT_TYPE_NOSNIFF: bool = env.bool(
    "DJANGO_SECURE_CONTENT_TYPE_NOSNIFF",
    default=True,
)

# ⚠️ Setting overrides for PRODUCTION

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#default-from-email
DEFAULT_FROM_EMAIL: str = env(
    "DJANGO_DEFAULT_FROM_EMAIL",
    default="SpectrumX Data System Gateway <noreply@sds.crc.nd.edu>",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#server-email
SERVER_EMAIL: str = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-subject-prefix
EMAIL_SUBJECT_PREFIX: str = env(
    "DJANGO_EMAIL_SUBJECT_PREFIX",
    default="[SpectrumX Data System Gateway] ",
)

# ⚠️ Setting overrides for PRODUCTION

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL regex.
ADMIN_URL: str = env("DJANGO_ADMIN_URL")

# Anymail
# ------------------------------------------------------------------------------
# https://anymail.readthedocs.io/en/stable/installation/#installing-anymail
# INSTALLED_APPS.extend(["anymail"])
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
# https://anymail.readthedocs.io/en/stable/installation/#anymail-settings-reference
# https://anymail.readthedocs.io/en/stable/esps/mailgun/
# EMAIL_BACKEND: str = "anymail.backends.mailgun.EmailBackend"
# ANYMAIL: dict[str, str] = {
#     "MAILGUN_API_KEY": env("MAILGUN_API_KEY"),
#     "MAILGUN_SENDER_DOMAIN": env("MAILGUN_DOMAIN"),
#     "MAILGUN_API_URL": env("MAILGUN_API_URL", default="https://api.mailgun.net/v3"),
# }

# ⚠️ Setting overrides for PRODUCTION

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "verbose": {
            "format": "%(levelname)s %(asctime)s %(module)s "
            "%(process)d %(thread)d %(message)s",
        },
    },
    "handlers": {
        "mail_admins": {
            "level": "ERROR",
            "filters": ["require_debug_false"],
            "class": "django.utils.log.AdminEmailHandler",
        },
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {"level": "DEBUG", "handlers": ["console"]},
    "loggers": {
        "django.request": {
            "handlers": ["mail_admins"],
            "level": "ERROR",
            "propagate": True,
        },
        "django.security.DisallowedHost": {
            "level": "ERROR",
            "handlers": ["console", "mail_admins"],
            "propagate": True,
        },
    },
}

# ⚠️ Setting overrides for PRODUCTION

# SENTRY
# ------------------------------------------------------------------------------
# https://docs.sentry.io/platforms/python/guides/django/
#   The following parts of this Django project are monitored:
#       + Middleware stack
#       + Signals
#       + Database queries
#       + Redis commands
#       + Access to Django caches
SENTRY_DSN: str = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk

    _hostname: str = gethostname()
    _is_staging: bool = "-qa" in _hostname or "-dev" in _hostname

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment="staging" if _is_staging else "production",
        # whether to add data like request headers and IP for users, for more info
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/
        send_default_pii=False,
    )

# DJANGO-REST-FRAMEWORK
# -------------------------------------------------------------------------------
# Tools that generate code samples can use SERVERS to point to the correct domain
SPECTACULAR_SETTINGS["SERVERS"] = [
    {"url": "https://sds.crc.nd.edu", "description": "Production server"},
]
# ------------------------------------------------------------------------------

# ⚠️ Setting overrides for PRODUCTION

# BUSINESS LOGIC
# ------------------------------------------------------------------------------
# Whether new users are approved to generate API keys on creation or not.
SDS_NEW_USERS_APPROVED_ON_CREATION: bool = env.bool(
    "SDS_NEW_USERS_APPROVED_ON_CREATION",
    default=False,
)
