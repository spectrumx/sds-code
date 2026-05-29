"""Context processors for the whole SDS Gateway project."""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from typing import Literal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.utils import OperationalError
from django.db.utils import ProgrammingError
from django.http import HttpRequest

logger = logging.getLogger(__name__)


def _load_version() -> dict[str, str]:
    """Load version info from version.json shipped with the build.

    In CI/CD this file is updated with the current git commit hash before
    the Docker image is built.  Falls back to the environment variable
    SDS_COMMIT_HASH or a hardcoded placeholder.
    """
    version_path = Path(__file__).parent.parent / "version.json"
    if version_path.is_file():
        try:
            data = json.loads(version_path.read_text())
            commit = data.get("commit", "unknown")
            version = data.get("version", "unknown")
            build_date = data.get("build_date", "unknown")
            logger.info(
                "version info loaded: commit=%s version=%s build_date=%s",
                commit,
                version,
                build_date,
            )
        except (OSError, json.JSONDecodeError):
            logger.warning(
                "failed to parse version file at %s",
                version_path,
                exc_info=True,
            )
        else:
            return {"commit": commit, "version": version}

    # File missing or unparseable — try env var fallback.
    if not version_path.is_file():
        logger.warning("version file not found at %s", version_path)
    commit = os.environ.get("SDS_COMMIT_HASH", "unknown")
    return {"commit": commit, "version": commit}


def _latest_admin_monitoring_status() -> dict[str, Any] | None:
    try:
        from sds_gateway.monitoring.models import SystemHealthSnapshot  # noqa: PLC0415

        return SystemHealthSnapshot.latest_snapshot_payload()
    except (ImportError, LookupError, OperationalError, ProgrammingError):
        logger.warning("failed to load admin monitoring status", exc_info=True)
        return None


def app_settings(_request: HttpRequest) -> dict[str, Any]:
    """Expose application-wide settings in templates."""
    return {
        "VISUALIZATIONS_ENABLED": settings.VISUALIZATIONS_ENABLED,
        "ADMIN_CONSOLE_ENV": settings.ADMIN_CONSOLE_ENV,
        "ADMIN_MONITORING_STATUS": _latest_admin_monitoring_status(),
    }


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


def static_cache_busting(_request: HttpRequest) -> dict[str, Any]:
    """Expose a version string for cache-busting static assets and navbar display.

    Returns the version tag (e.g. ``v0.1.19-8-g4bf9097f``) from version.json,
    which includes both the nearest release tag and the commit count/hash.
    Falls back to ``SDS_COMMIT_HASH`` or ``"unknown"``.
    """
    version = _load_version()
    return {"STATIC_CACHE_BUSTING_VERSION": version["version"]}
