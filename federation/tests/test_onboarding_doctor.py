"""Regression tests for federation-doctor.sh checks (fixture-driven)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = FEDERATION_ROOT / "scripts" / "federation-doctor.sh"


def run_doctor(
    *,
    federation_toml: Path,
    django_env: Path,
    shared_env: Path,
    site_env: Path,
    check: str,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "SDS_ENV": "production",
        "FEDERATION_DOCTOR_FEDERATION_TOML": str(federation_toml),
        "FEDERATION_DOCTOR_DJANGO_ENV": str(django_env),
        "FEDERATION_DOCTOR_SHARED_ENV": str(shared_env),
        "FEDERATION_DOCTOR_SITE_ENV": str(site_env),
        "FEDERATION_DOCTOR_SKIP_DB": "1",
        "FEDERATION_DOCTOR_SKIP_DNS": "1",
    }
    if extra_env:
        env.update(extra_env)
    return subprocess.run(  # noqa: S603
        ["/bin/bash", str(DOCTOR), check],
        cwd=FEDERATION_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def doctor_fixtures(tmp_path: Path) -> dict[str, Path]:
    toml = tmp_path / "federation.toml"
    toml.write_text(
        "[site]\n"
        'name = "crc"\n'
        'fqdn = "sds.crc.nd.edu"\n'
        'display_name = "CRC"\n'
        'sync_service_url = "https://sds.crc.nd.edu/sync"\n',
        encoding="utf-8",
    )
    django = tmp_path / "django.env"
    django.write_text(
        "FEDERATION_SITE_NAME=crc\nSDS_SITE_FQDN=sds.crc.nd.edu\n",
        encoding="utf-8",
    )
    shared = tmp_path / "federation-shared.env"
    shared.write_text(
        "FEDERATION_SYNC_DRF_TOKEN=01234567890123456789012345678901234567890\n",
        encoding="utf-8",
    )
    site = tmp_path / "site.env"
    site.write_text(
        "FEDERATION_SYNC_SERVICE_URL=https://sds.crc.nd.edu/sync\n",
        encoding="utf-8",
    )
    return {
        "toml": toml,
        "django": django,
        "shared": shared,
        "site": site,
    }


@pytest.mark.regression
def test_doctor_identity_passes(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="identity",
    )
    assert result.returncode == 0


@pytest.mark.regression
def test_doctor_identity_fails_on_mismatch(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    f["django"].write_text("FEDERATION_SITE_NAME=other\n", encoding="utf-8")
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="identity",
    )
    assert result.returncode != 0
    assert "FEDERATION_SITE_NAME" in result.stderr


@pytest.mark.regression
def test_doctor_token_fails_on_short_token(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    f["shared"].write_text("FEDERATION_SYNC_DRF_TOKEN=short\n", encoding="utf-8")
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="token",
    )
    assert result.returncode != 0
    assert "40 characters" in result.stderr


@pytest.mark.regression
def test_doctor_sync_url_reads_quoted_site_env(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    f["toml"].write_text(
        '[site]\nname = "fed1"\nfqdn = "fed1.example.edu"\n',
        encoding="utf-8",
    )
    f["site"].write_text(
        'FEDERATION_SYNC_SERVICE_URL="https://fed1.example.edu/sync"\n',
        encoding="utf-8",
    )
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="sync_url",
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.regression
def test_doctor_sync_url_fails_on_port_8001(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    f["toml"].write_text(
        '[site]\nname = "crc"\nfqdn = "sds.crc.nd.edu"\n'
        'sync_service_url = "http://sds.crc.nd.edu:8001/sync"\n',
        encoding="utf-8",
    )
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="sync_url",
    )
    assert result.returncode != 0
    assert ":8001" in result.stderr


@pytest.mark.regression
def test_doctor_sync_url_allows_port_8001_local(
    doctor_fixtures: dict[str, Path],
) -> None:
    f = doctor_fixtures
    f["toml"].write_text(
        '[site]\nname = "crc"\nfqdn = "sds.localhost"\n'
        'sync_service_url = "http://localhost:8001/sync"\n',
        encoding="utf-8",
    )
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="sync_url",
        extra_env={"SDS_ENV": "local"},
    )
    assert result.returncode == 0
