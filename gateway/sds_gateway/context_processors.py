"""Context processors for the whole SDS Gateway project."""

from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone

from django.http import HttpRequest


@dataclass
class Notification:
    user_message: str
    admin_message: str
    expires_on: datetime


eastern = timezone(timedelta(hours=-5))


def system_notifications(_request: HttpRequest) -> dict[str, list[Notification]]:
    """Return global system notifications to users for the SDS Gateway."""
    notifications = [
        Notification(
            user_message="SDS is scheduled for maintenance on "
            "January 11, 2025 from 7AM to 11AM ET.",
            admin_message="Scheduled CRC maintenance.",
            expires_on=datetime(2025, 1, 11, 11, 0, 0, tzinfo=eastern),
        ),
    ]

    # filter expired notifications
    notifications = [n for n in notifications if n.expires_on > datetime.now(eastern)]

    return {"system_notifications": notifications}
