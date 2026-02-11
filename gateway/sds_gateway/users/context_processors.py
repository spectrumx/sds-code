from django.conf import settings


def allauth_settings(request):
    """Expose some settings from django-allauth in templates."""
    return {
        "ACCOUNT_ALLOW_REGISTRATION": settings.ACCOUNT_ALLOW_REGISTRATION,
        "LOGIN_BY_CODE_ENABLED": getattr(
            settings, "ACCOUNT_LOGIN_BY_CODE_ENABLED", False
        ),
        "PASSKEY_LOGIN_ENABLED": getattr(settings, "MFA_PASSKEY_LOGIN_ENABLED", False),
        "SOCIALACCOUNT_ONLY": getattr(settings, "SOCIALACCOUNT_ONLY", False),
        "SOCIALACCOUNT_ENABLED": "allauth.socialaccount" in settings.INSTALLED_APPS,
    }
