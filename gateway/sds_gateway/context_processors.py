"""Context processors for the whole SDS Gateway project."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.http import HttpRequest


@dataclass
class Notification:
    user_message: str
    admin_message: str
    expires_on: datetime
    level: Literal["info", "warning", "danger"] = "warning"
    # level is one of the alert-* classes from Bootstrap


eastern = ZoneInfo("America/New_York")


def system_notifications(_request: HttpRequest) -> dict[str, list[Notification]]:
    """Return global system notifications to users for the SDS Gateway."""
    notifications = [
        Notification(
            user_message="SDS is scheduled for maintenance on "
            "Friday, May 16, 2025 from 7 AM to 1 PM ET and it might be "
            "unavailable during this time period.",
            admin_message="Scheduled CRC maintenance.",
            level="warning",
            expires_on=datetime(2025, 5, 16, 13, 0, 0, tzinfo=eastern),
        ),
    ]

    # filter expired notifications
    notifications = [n for n in notifications if n.expires_on > datetime.now(eastern)]

    return {"system_notifications": notifications}


def branding(_request: HttpRequest) -> dict[str, str | None]:
    """Return branding settings to templates."""
    return {
        "SDS_BRAND_IMAGE_URL": settings.SDS_BRAND_IMAGE_URL,
        "SDS_BRANDED_SITE_NAME": settings.SDS_BRANDED_SITE_NAME,
        "SDS_FULL_INSTITUTION_NAME": settings.SDS_FULL_INSTITUTION_NAME,
        "SDS_PROGRAMMATIC_SITE_NAME": settings.SDS_PROGRAMMATIC_SITE_NAME,
        "SDS_SHORT_INSTITUTION_NAME": settings.SDS_SHORT_INSTITUTION_NAME,
        "SDS_SITE_FQDN": settings.SDS_SITE_FQDN,
    }
