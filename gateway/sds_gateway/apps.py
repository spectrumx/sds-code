"""AppConfig for the SDS Gateway project.

Auto-populates version.json at startup so that commit, version, and build_date
are always set to real values when the app runs — whether in local development
or inside a production Docker container.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from datetime import UTC
from datetime import datetime
from pathlib import Path

from django.apps import AppConfig

logger = logging.getLogger(__name__)

VERSION_JSON_PATH = Path(__file__).resolve().parent.parent / "version.json"
_GIT_PATH: str | None = shutil.which("git")


def _get_git_commit() -> str | None:
    """Return the short git commit hash, or None if git is unavailable."""
    if _GIT_PATH is None:
        logger.debug("git not available; will try fallbacks for version.json")
        return None
    try:
        return subprocess.run(  # noqa: S603 -- _GIT_PATH resolved from system PATH
            [_GIT_PATH, "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            shell=False,
        ).stdout.strip()
    except subprocess.SubprocessError:
        logger.debug("git not available; will try fallbacks for version.json")
        return None


def _get_git_version() -> str | None:
    """Return the most recent git tag description, or None if unavailable."""
    if _GIT_PATH is None:
        return None
    try:
        return subprocess.run(  # noqa: S603 -- _GIT_PATH resolved from system PATH
            [_GIT_PATH, "describe", "--tags", "--always"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
            shell=False,
        ).stdout.strip()
    except subprocess.SubprocessError:
        return None


def _ensure_version_json() -> None:
    """Populate version.json with real values where possible.

    Resolution order (first wins):
      1. Git metadata (available in local dev / CI)
      2. Environment variable ``SDS_COMMIT_HASH``
      3. If file already exists (e.g. written by Dockerfile during build),
         leave it untouched.
      4. Hard-coded ``"unknown"`` placeholders as last resort.
    """
    commit = _get_git_commit()
    version = _get_git_version()

    if commit and version:
        # Git is available — write fresh values (local dev / CI).
        data = {
            "commit": commit,
            "version": version,
            "build_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        VERSION_JSON_PATH.write_text(json.dumps(data, indent=4) + "\n")
        logger.debug(
            "version.json updated from git: commit=%s version=%s",
            commit,
            version,
        )
        return

    if commit:
        # Got commit but not version tag — use commit as version too.
        data = {
            "commit": commit,
            "version": commit,
            "build_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        VERSION_JSON_PATH.write_text(json.dumps(data, indent=4) + "\n")
        return

    # Git is not available.  Try environment variable.
    env_commit = os.environ.get("SDS_COMMIT_HASH")
    if env_commit:
        data = {
            "commit": env_commit,
            "version": env_commit,
            "build_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        VERSION_JSON_PATH.write_text(json.dumps(data, indent=4) + "\n")
        return

    # Git unavailable + no env var.  If the file already exists (e.g.
    # Dockerfile wrote it during the build) AND has real values, keep it.
    # If it has placeholder values ("none"), try env var fallback.
    if VERSION_JSON_PATH.exists():
        try:
            existing = json.loads(VERSION_JSON_PATH.read_text())
            if existing.get("commit", "none") not in ("none", "unknown"):
                logger.debug(
                    "version.json already exists with real values; leaving intact"
                )
                return
            logger.debug(
                "version.json exists but has placeholder values; checking fallbacks"
            )
        except (OSError, json.JSONDecodeError):
            logger.warning("existing version.json is corrupt; will overwrite")

    data = {
        "commit": "unknown",
        "version": "unknown",
        "build_date": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    VERSION_JSON_PATH.write_text(json.dumps(data, indent=4) + "\n")
    logger.warning("version.json written with placeholders (no git, no env)")


class SdsGatewayConfig(AppConfig):
    """Top-level AppConfig for the SDS Gateway project."""

    name = "sds_gateway"
    verbose_name = "SDS Gateway"

    def ready(self) -> None:
        _ensure_version_json()
