"""Regression tests for federation-doctor.sh checks (fixture-driven)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

FEDERATION_ROOT = Path(__file__).resolve().parents[1]
DOCTOR = FEDERATION_ROOT / "scripts" / "bin" / "federation-doctor.sh"


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
        "FEDERATION_SYNC_DRF_TOKEN=0123456789012345678901234567890123456789\n",
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
def test_doctor_sync_url_reads_quoted_site_env(
    doctor_fixtures: dict[str, Path],
) -> None:
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


@pytest.mark.regression
def test_doctor_traefik_routes_passes(doctor_fixtures: dict[str, Path], tmp_path: Path) -> None:
    f = doctor_fixtures
    traefik = tmp_path / "conf.d"
    traefik.mkdir()
    (traefik / "site-sync.toml").write_text(
        'rule = "Host(`sds.crc.nd.edu`) && PathPrefix(`/sync`)"\n',
        encoding="utf-8",
    )
    (traefik / "site-wellknown.toml").write_text(
        'rule = "Host(`sds.crc.nd.edu`) && Path(`/.well-known/sds-federation.json`)"\n',
        encoding="utf-8",
    )
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="traefik_routes",
        extra_env={"FEDERATION_DOCTOR_TRAEFIK_CONF_DIR": str(traefik)},
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.regression
def test_doctor_traefik_routes_fails_without_wellknown(
    doctor_fixtures: dict[str, Path],
    tmp_path: Path,
) -> None:
    f = doctor_fixtures
    traefik = tmp_path / "conf.d"
    traefik.mkdir()
    (traefik / "site-sync.toml").write_text(
        'rule = "Host(`sds.crc.nd.edu`) && PathPrefix(`/sync`)"\n',
        encoding="utf-8",
    )
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="traefik_routes",
        extra_env={"FEDERATION_DOCTOR_TRAEFIK_CONF_DIR": str(traefik)},
    )
    assert result.returncode != 0
    assert "well-known" in result.stderr.lower()


@pytest.mark.regression
def test_doctor_registry_apply_ready_requires_pubkey(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    f["site"].write_text(
        "FEDERATION_REGISTRY_URL=https://sds.crc.nd.edu/.well-known/sds-registry\n",
        encoding="utf-8",
    )
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="registry_apply_ready",
        extra_env={
            "FEDERATION_DOCTOR_REGISTRY_PUBKEY_HOST": str(
                f["site"].parent / "missing-sds-registry.pub.pem"
            ),
        },
    )
    assert result.returncode != 0
    assert "registry public key" in result.stderr


@pytest.mark.regression
def test_doctor_preflight_apply_prints_fqdn(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    result = subprocess.run(  # noqa: S603
        ["/bin/bash", str(DOCTOR), "preflight_apply"],
        cwd=FEDERATION_ROOT,
        env={
            **os.environ,
            "SDS_ENV": "production",
            "FEDERATION_DOCTOR_FEDERATION_TOML": str(f["toml"]),
            "FEDERATION_DOCTOR_DJANGO_ENV": str(f["django"]),
            "FEDERATION_DOCTOR_SHARED_ENV": str(f["shared"]),
            "FEDERATION_DOCTOR_SITE_ENV": str(f["site"]),
            "FEDERATION_DOCTOR_SKIP_DB": "1",
            "FEDERATION_DOCTOR_SKIP_DNS": "1",
            "FEDERATION_DOCTOR_SKIP_TRAEFIK": "1",
            "FEDERATION_DOCTOR_SKIP_PUBLIC": "1",
            "FEDERATION_DOCTOR_SKIP_REGISTRY": "1",
            "FEDERATION_DOCTOR_SKIP_NETWORKS": "1",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "Registry application FQDN (use exactly): sds.crc.nd.edu" in result.stdout


@pytest.mark.regression
def test_doctor_identity_fails_site_env_fqdn_mismatch(doctor_fixtures: dict[str, Path]) -> None:
    f = doctor_fixtures
    f["site"].write_text('SDS_SITE_FQDN="other.example.edu"\n', encoding="utf-8")
    result = run_doctor(
        federation_toml=f["toml"],
        django_env=f["django"],
        shared_env=f["shared"],
        site_env=f["site"],
        check="identity",
    )
    assert result.returncode != 0
    assert "site.env" in result.stderr
