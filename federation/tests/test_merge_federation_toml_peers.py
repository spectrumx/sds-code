"""Tests for merge_federation_toml_peers.py."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
MERGE = FEDERATION_ROOT / "scripts" / "merge_federation_toml_peers.py"


@pytest.mark.regression
def test_merge_preserves_bootstrap_peer_ca_on_rerender(tmp_path: Path) -> None:
    existing = tmp_path / "existing.toml"
    rendered = tmp_path / "rendered.toml"
    existing.write_text(
        """
[site]
name = "fed1"
fqdn = "fed1.example.edu"

[[peers]]
name = "crc"
fqdn = "sds.crc.nd.edu"
display_name = "CRC"
gateway_api_base = "https://sds.crc.nd.edu/api/v1"
sync_service_url = "https://sds.crc.nd.edu/sync/"
ca_cert_path = "/etc/sds/certs/crc-ca.pem"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    rendered.write_text(
        """
[site]
name = "fed1"
fqdn = "fed1.example.edu"

[[peers]]
name = "crc"
fqdn = "sds.crc.nd.edu"
display_name = "CRC"
gateway_api_base = "https://sds.crc.nd.edu/api/v1"
sync_service_url = "https://sds.crc.nd.edu/sync/"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    out_path = tmp_path / "out.toml"
    subprocess.run(
        [sys.executable, str(MERGE), str(rendered), str(existing), str(out_path)],
        check=True,
    )
    text = out_path.read_text(encoding="utf-8")
    assert 'ca_cert_path = "/etc/sds/certs/crc-ca.pem"' in text
