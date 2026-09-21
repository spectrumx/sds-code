"""Tests for site.env shell-safe rendering."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = FEDERATION_ROOT / "scripts"


@pytest.mark.regression
def test_site_env_sources_display_name_with_spaces(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "SDS_SITE_NAME": "crc",
        "SDS_SITE_FQDN": "sds.localhost",
        "SDS_SITE_DISPLAY_NAME": "Local CRC",
        "FEDERATION_SYNC_SERVICE_URL": "http://localhost:8001/sync",
        "GATEWAY_INTERNAL_BASE_URL": "http://sds-gateway-local-app:8000/api/v1",
        "REDIS_URL": "redis://sds-gateway-local-redis:6379/0",
        "FEDERATION_PEER_CA_PATH": "",
    }
    dest = tmp_path / "site.env"
    subprocess.run(  # noqa: S603
        [sys.executable, str(SCRIPTS / "write_site_env.py"), str(dest)],
        env=env,
        check=True,
    )
    result = subprocess.run(  # noqa: S603
        [
            "/bin/bash",
            "-c",
            f'set -euo pipefail; source "{dest}"; printf "%s" "$SDS_SITE_DISPLAY_NAME"',
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout == "Local CRC"
