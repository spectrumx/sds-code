"""
With these settings, tests run faster.
"""

from .base import *  # noqa: F403 pylint: disable=wildcard-import,unused-wildcard-import
from .base import TEMPLATES
from .base import env

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="i7lLKZqZCyqDkR4pxy8AmfYg2Jw5DWqJ92YdglKYZGchZQnm5icgqft16OWw8Cf5",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#test-runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# PASSWORDS
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#password-hashers
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-backend
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# DEBUGGING FOR TEMPLATES
# ------------------------------------------------------------------------------
TEMPLATES[0]["OPTIONS"]["debug"] = True  # type: ignore[index]

# MEDIA
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "http://media.testserver"
# django-webpack-loader
# ------------------------------------------------------------------------------
try:
    WEBPACK_LOADER["DEFAULT"]["LOADER_CLASS"] = (  # noqa: F405
        "webpack_loader.loaders.FakeWebpackLoader"
    )
except NameError as err:
    __MSG = "WEBPACK_LOADER is not defined. You must define it in your settings."
    raise ImportError(__MSG) from err
# Your stuff...
# ------------------------------------------------------------------------------
