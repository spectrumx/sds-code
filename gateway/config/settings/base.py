"""Base settings to build other settings files upon."""
# ruff: noqa: ERA001

import random
import string
from pathlib import Path
from typing import Any

from environs import env

from config.settings.logs import ColoredFormatter

__rng = random.SystemRandom()


def __get_random_token(length: int) -> str:
    """Generates a random token of 40 characters."""
    return "".join(
        __rng.choice(string.ascii_letters + string.digits) for _ in range(length)
    )


env.read_env()

BASE_DIR: Path = Path(__file__).resolve(strict=True).parent.parent.parent

API_VERSION: str = env.str("API_VERSION", default="v1")

OPENSEARCH_HOST: str = env.str("OPENSEARCH_HOST", default="localhost")
OPENSEARCH_PORT: str = env.str("OPENSEARCH_PORT", default="9200")
OPENSEARCH_USER: str = env.str("OPENSEARCH_USER", default="django")
OPENSEARCH_PASSWORD: str = env.str("OPENSEARCH_PASSWORD", default="admin")
OPENSEARCH_INITIAL_ADMIN_PASSWORD: str = env.str(
    "OPENSEARCH_INITIAL_ADMIN_PASSWORD",
    default="admin",
)
OPENSEARCH_USE_SSL: bool = env.bool("OPENSEARCH_USE_SSL", default=False)
OPENSEARCH_VERIFY_CERTS: bool = env.bool("OPENSEARCH_VERIFY_CERTS", default=False)
OPENSEARCH_CA_CERTS: str | None = env.str("OPENSEARCH_CA_CERTS", default=None)

# MinIO configuration
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
MINIO_ENDPOINT_URL = env.str("MINIO_ENDPOINT_URL", default="minio:9000")
MINIO_STORAGE_USE_HTTPS = env.bool("MINIO_STORAGE_USE_HTTPS", default=False)

AWS_ACCESS_KEY_ID: str = env.str("AWS_ACCESS_KEY_ID", default="minioadmin")
AWS_SECRET_ACCESS_KEY: str = env.str("AWS_SECRET_ACCESS_KEY", default="miniopassword")
AWS_STORAGE_BUCKET_NAME: str = env.str("AWS_STORAGE_BUCKET_NAME", default="spectrumx")
AWS_S3_ENDPOINT_URL: str = env.str(
    "AWS_S3_ENDPOINT_URL",
    default="http://minio:9000",
)
AWS_S3_REGION_NAME: str = "us-east-1"
AWS_S3_SIGNATURE_VERSION: str = "s3v4"
AWS_S3_FILE_OVERWRITE: bool = False
AWS_DEFAULT_ACL: str | None = None

# sds_gateway/
APPS_DIR: Path = BASE_DIR / "sds_gateway"

READ_DOT_ENV_FILE: bool = env.bool("DJANGO_READ_DOT_ENV_FILE", default=False)
if READ_DOT_ENV_FILE:
    # OS environment variables take precedence over variables from .env
    env.read_env(str(BASE_DIR / ".env"))

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG: bool = env.bool("DJANGO_DEBUG", False)
# Local time zone. Choices are
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# though not all of them may be available with every OS.
# In Windows, this must be set to your system time zone.
TIME_ZONE: str = "America/New_York"
# https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE: str = "en-us"
# https://docs.djangoproject.com/en/dev/ref/settings/#languages
# from django.utils.translation import gettext_lazy as _
# LANGUAGES = [
#     ('en', _('English')),
#     ('fr-fr', _('French')),
#     ('pt-br', _('Portuguese')),
# ]
# https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID: int = 1
# https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#locale-paths
LOCALE_PATHS: list[str] = [str(BASE_DIR / "locale")]

# DATABASES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES: dict[str, Any] = {"default": env.dj_db_url("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True
# https://docs.djangoproject.com/en/stable/ref/settings/#std:setting-DEFAULT_AUTO_FIELD
DEFAULT_AUTO_FIELD: str = "django.db.models.BigAutoField"

# URLS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#root-urlconf
ROOT_URLCONF: str = "config.urls"
# https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION: str = "config.wsgi.application"

# APPS
# ------------------------------------------------------------------------------
DJANGO_APPS: list[str] = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",  # handy template tags used in allauth
    "django.contrib.admin",
    "django.forms",
    "storages",
    "django_extensions",  # show_urls, validate_templates, ...
]
THIRD_PARTY_APPS: list[str] = [
    "crispy_forms",
    "crispy_bootstrap5",
    "allauth",
    "allauth.account",
    "allauth.mfa",
    "allauth.socialaccount",
    # "django_celery_beat",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_api_key",
    "corsheaders",
    "drf_spectacular",
    "webpack_loader",
]

LOCAL_APPS: list[str] = [
    "sds_gateway.users",
    "sds_gateway.api_methods",
    # Your stuff: custom apps go here
]
# https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS: list[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIGRATIONS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#migration-modules
MIGRATION_MODULES: dict[str, str] = {"sites": "sds_gateway.contrib.sites.migrations"}

# AUTHENTICATION
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#authentication-backends
AUTHENTICATION_BACKENDS: list[str] = [
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-user-model
AUTH_USER_MODEL: str = "users.User"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-redirect-url
LOGIN_REDIRECT_URL: str = "users:redirect"
# https://docs.djangoproject.com/en/dev/ref/settings/#login-url
LOGIN_URL: str = "account_login"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS: list[str] = [
    # https://docs.djangoproject.com/en/dev/topics/auth/passwords/#using-argon2-with-django
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]
# https://docs.djangoproject.com/en/dev/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# MIDDLEWARE
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#middleware
MIDDLEWARE: list[str] = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "allauth.account.middleware.AccountMiddleware",
]

# STATIC
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT: str = str(BASE_DIR / "staticfiles")
# https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL: str = "/static/"
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS: list[str] = [str(APPS_DIR / "static")]
# https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS: list[str] = [
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT: str = str(APPS_DIR / "media")
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL: str = "/media/"

# TEMPLATES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES: list[dict[str, Any]] = [
    {
        # https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # https://docs.djangoproject.com/en/dev/ref/settings/#dirs
        "DIRS": [str(APPS_DIR / "templates")],
        # https://docs.djangoproject.com/en/dev/ref/settings/#app-dirs
        "APP_DIRS": True,
        "OPTIONS": {
            # https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                "sds_gateway.users.context_processors.allauth_settings",
                "sds_gateway.context_processors.system_notifications",
            ],
        },
    },
]

# https://docs.djangoproject.com/en/dev/ref/settings/#form-renderer
FORM_RENDERER: str = "django.forms.renderers.TemplatesSetting"

# http://django-crispy-forms.readthedocs.io/en/latest/install.html#template-packs
CRISPY_TEMPLATE_PACK: str = "bootstrap5"
CRISPY_ALLOWED_TEMPLATE_PACKS: str = "bootstrap5"

# FIXTURES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#fixture-dirs
FIXTURE_DIRS: tuple[str] = (str(APPS_DIR / "fixtures"),)

# SECURITY
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#session-cookie-httponly
SESSION_COOKIE_HTTPONLY: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#csrf-cookie-httponly
CSRF_COOKIE_HTTPONLY: bool = True
# https://docs.djangoproject.com/en/dev/ref/settings/#x-frame-options
X_FRAME_OPTIONS: str = "DENY"

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND: str = env(
    "DJANGO_EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#email-timeout
EMAIL_TIMEOUT: int = 5

# ADMIN
# ------------------------------------------------------------------------------
# Django Admin URL.
ADMIN_URL: str = "admin/"
# https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS: list[tuple[str, ...]] = [
    (
        """Center for Research Computing | University of Notre Dame""",
        "crcsupport@nd.edu",
    ),
]
# https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS: list[tuple[str, ...]] = ADMINS
# https://cookiecutter-django.readthedocs.io/en/latest/settings.html#other-environment-settings
# Force the `admin` sign in process to go through the `django-allauth` workflow
DJANGO_ADMIN_FORCE_ALLAUTH: bool = env.bool("DJANGO_ADMIN_FORCE_ALLAUTH", default=False)

# LOGGING
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#logging
# See https://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING: dict[str, Any] = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "colored": {
            "()": ColoredFormatter,
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "colored",
        },
    },
    "root": {"level": "DEBUG", "handlers": ["console"]},
}

# CELERY
# ------------------------------------------------------------------------------
if USE_TZ:
    # https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-timezone
    CELERY_TIMEZONE: str = TIME_ZONE

# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-broker_url
CELERY_BROKER_URL: str = env("CELERY_BROKER_URL", default="redis://redis:6379/0")
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_backend
CELERY_RESULT_BACKEND: str = CELERY_BROKER_URL
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-extended
CELERY_RESULT_EXTENDED: bool = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-always-retry
# https://github.com/celery/celery/pull/6122
CELERY_RESULT_BACKEND_ALWAYS_RETRY: bool = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#result-backend-max-retries
CELERY_RESULT_BACKEND_MAX_RETRIES: int = 10
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-accept_content
CELERY_ACCEPT_CONTENT: list[str] = ["json"]
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-task_serializer
CELERY_TASK_SERIALIZER: str = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std:setting-result_serializer
CELERY_RESULT_SERIALIZER: str = "json"
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-time-limit
CELERY_TASK_TIME_LIMIT: int = 5 * 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-soft-time-limit
CELERY_TASK_SOFT_TIME_LIMIT: int = 60
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#worker-send-task-events
CELERY_WORKER_SEND_TASK_EVENTS: bool = True
# https://docs.celeryq.dev/en/stable/userguide/configuration.html#std-setting-task_send_sent_event
CELERY_TASK_SEND_SENT_EVENT: bool = True

# django-allauth
# ------------------------------------------------------------------------------
# https://cookiecutter-django.readthedocs.io/en/latest/1-getting-started/settings.html
ACCOUNT_ALLOW_REGISTRATION: bool = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)

# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_AUTHENTICATION_METHOD: str = "email"
ACCOUNT_EMAIL_REQUIRED: bool = True
ACCOUNT_USERNAME_REQUIRED: bool = False
ACCOUNT_USER_MODEL_USERNAME_FIELD: str | None = None
ACCOUNT_EMAIL_VERIFICATION: str = "none"
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_LOGOUT_ON_GET: bool = True
# https://docs.allauth.org/en/latest/account/configuration.html
ACCOUNT_ADAPTER: str = "sds_gateway.users.adapters.AccountAdapter"

# https://docs.allauth.org/en/latest/account/forms.html
ACCOUNT_FORMS: dict[str, str] = {
    "signup": "sds_gateway.users.forms.UserSignupForm",
}

# https://docs.allauth.org/en/latest/socialaccount/configuration.html
SOCIALACCOUNT_ADAPTER: str = "sds_gateway.users.adapters.SocialAccountAdapter"
SOCIALACCOUNT_FORMS: dict[str, str] = {
    "signup": "sds_gateway.users.forms.UserSocialSignupForm",
}

# django-rest-framework
# -------------------------------------------------------------------------------
# django-rest-framework - https://www.django-rest-framework.org/api-guide/settings/
REST_FRAMEWORK: dict[str, str | tuple[str, ...]] = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework.authentication.BasicAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
        "sds_gateway.api_methods.authentication.APIKeyAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# django-cors-headers - https://github.com/adamchainz/django-cors-headers#setup
CORS_URLS_REGEX: str = r"^/api/.*$"

# By Default swagger ui is available only to admin user(s). You can change
# permission classes to change that. See more configuration options at
# https://drf-spectacular.readthedocs.io/en/latest/settings.html#settings
SPECTACULAR_SETTINGS: dict[str, Any] = {
    "TITLE": "SpectrumX Data System Gateway API",
    "DESCRIPTION": "Documentation of API endpoints of SpectrumX Data System Gateway",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "POSTPROCESSING_HOOKS": [
        "sds_gateway.api_methods.utils.spectacular_hooks.remove_irrelevant_auth_schemes",
    ],
    "SCHEMA_PATH_PREFIX": f"/api/{API_VERSION}",
    "SERVE_PUBLIC": True,
    "SERVE_AUTHENTICATION": None,
}
# django-webpack-loader
# ------------------------------------------------------------------------------
WEBPACK_LOADER: dict[str, dict[str, Any]] = {
    "DEFAULT": {
        "CACHE": not DEBUG,
        "STATS_FILE": BASE_DIR / "webpack-stats.json",
        "POLL_INTERVAL": 0.1,
        "IGNORE": [r".+\.hot-update.js", r".+\.map"],
    },
}
# ------------------------------------------------------------------------------

# AUTH0
# ------------------------------------------------------------------------------
SOCIALACCOUNT_PROVIDERS = {
    "auth0": {
        # https://docs.allauth.org/en/dev/socialaccount/providers/auth0.html#auth0
        "AUTH0_URL": env("AUTH0_DOMAIN"),
        "OAUTH_PKCE_ENABLED": True,
        "SCOPE": [
            "openid",
            "profile",
            "email",
        ],
    },
}

# Add 'allauth.socialaccount.providers.auth0' to INSTALLED_APPS
INSTALLED_APPS += ["allauth.socialaccount.providers.auth0"]
SOCIALACCOUNT_LOGIN_ON_GET: bool = True

# SVI Server API Key
SVI_SERVER_EMAIL: str = env(
    "SVI_SERVER_EMAIL",
    default="svi-server@spectrumx.crc.nd.edu",
)

TOKEN_LENGTH: int = 40
SVI_SERVER_API_KEY: str = env(
    "SVI_SERVER_API_KEY", default=__get_random_token(TOKEN_LENGTH)
)
assert len(SVI_SERVER_API_KEY) == TOKEN_LENGTH, (
    f"SVI_SERVER_API_KEY must be {TOKEN_LENGTH} characters long. "
    "Please check your environment variable."
)

# BUSINESS LOGIC
# ------------------------------------------------------------------------------
# Whether new users are approved to generate API keys on creation or not.
SDS_NEW_USERS_APPROVED_ON_CREATION: bool = env.bool(
    "SDS_NEW_USERS_APPROVED_ON_CREATION",
    default=False,
)
