"""Context processors for the whole SDS Gateway project."""

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from typing import Literal

from django.http import HttpRequest


@dataclass
class Notification:
    user_message: str
    admin_message: str
    expires_on: datetime
    level: Literal["info", "warning", "danger"] = "warning"
    # level is one of the alert-* classes from Bootstrap


eastern = timezone(timedelta(hours=-5))


def system_notifications(_request: HttpRequest) -> dict[str, list[Notification]]:
    """Return global system notifications to users for the SDS Gateway."""
    notifications = [
        Notification(
            user_message="SDS is scheduled for maintenance on "
            "January 11, 2025 from 7AM to 11AM ET and it might be "
            "unavailable during this time period.",
            admin_message="Scheduled CRC maintenance.",
            level="warning",
            expires_on=datetime(2025, 1, 11, 11, 0, 0, tzinfo=eastern),
        ),
    ]

    # filter expired notifications
    notifications = [n for n in notifications if n.expires_on > datetime.now(eastern)]

    return {"system_notifications": notifications}
