"""Regression: load_site_env_for_render must not clobber exported site identity."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
SITE_ENV_SH = FEDERATION_ROOT / "scripts" / "lib" / "site_env.sh"


@pytest.mark.regression
def test_load_site_env_for_render_keeps_exported_site_name(tmp_path: Path) -> None:
    site_env = tmp_path / "site.env"
    site_env.write_text(
        'SDS_SITE_NAME="old-site"\n'
        'SDS_SITE_FQDN="old.example.edu"\n'
        'FEDERATION_PEER_CA_PATH="certs/ca.pem"\n',
        encoding="utf-8",
    )
    script = f"""
set -euo pipefail
FEDERATION_ROOT="{tmp_path}"
source "{SITE_ENV_SH}"
export SDS_SITE_NAME=new-site
export SDS_SITE_FQDN=new.example.edu
load_site_env_for_render
printf '%s|%s|%s' "$SDS_SITE_NAME" "$SDS_SITE_FQDN" "${{FEDERATION_PEER_CA_PATH:-}}"
"""
    out = subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "FEDERATION_ROOT": str(tmp_path)},
    )
    name, fqdn, ca = out.stdout.split("|", 2)
    assert name == "new-site"
    assert fqdn == "new.example.edu"
    assert ca == "certs/ca.pem"


@pytest.mark.regression
def test_public_sync_health_url_local_uses_host_port() -> None:
    script = f"""
set -euo pipefail
FEDERATION_ROOT="{FEDERATION_ROOT}"
SDS_ENV_TYPE=local
export FEDERATION_SYNC_SERVICE_URL=http://sds-federation-local-sync:8000/sync
source "{SITE_ENV_SH}"
public_sync_health_url
"""
    out = subprocess.run(  # noqa: S603
        ["/bin/bash", "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )
    assert out.stdout.strip() == "http://127.0.0.1:8001/sync/health"
