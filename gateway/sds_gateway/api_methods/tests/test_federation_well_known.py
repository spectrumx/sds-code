from __future__ import annotations

import json

import pytest
from django.test import Client
from django.urls import reverse

from sds_gateway.api_methods.federation.well_known import build_sds_federation_document
from sds_gateway.api_methods.federation.well_known import resolve_well_known_fetch_url


@pytest.mark.django_db
def test_sds_federation_well_known_endpoint(settings, client: Client) -> None:
    settings.ADMIN_CONSOLE_ENV = "production"
    settings.SDS_SITE_FQDN = "sds.example.edu"
    settings.FEDERATION_SITE_NAME = "example"
    settings.SDS_SITE_DISPLAY_NAME = "Example SDS"
    settings.API_VERSION = "v1"
    # Local compose often sets Docker DNS overrides; derive from FQDN for this case.
    settings.FEDERATION_GATEWAY_API_BASE = ""
    settings.FEDERATION_SYNC_SERVICE_URL = ""

    response = client.get(reverse("sds_federation_well_known"))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["fqdn"] == "sds.example.edu"
    assert payload["name"] == "example"
    assert payload["display_name"] == "Example SDS"
    assert payload["gateway_api_base"] == "https://sds.example.edu/api/v1"
    assert payload["sync_service_url"] == "https://sds.example.edu/sync/"
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_sds_federation_well_known_local_lab_defaults(client: Client, settings) -> None:
    settings.ADMIN_CONSOLE_ENV = "local"
    settings.SDS_SITE_FQDN = "sds.localhost"
    settings.FEDERATION_SITE_NAME = "crc"
    settings.SDS_SITE_DISPLAY_NAME = "Local CRC"
    settings.FEDERATION_GATEWAY_API_BASE = ""
    settings.FEDERATION_SYNC_SERVICE_URL = ""

    response = client.get(reverse("sds_federation_well_known"))

    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["gateway_api_base"] == "http://sds-gateway-local-app:8000/api/v1"
    assert payload["sync_service_url"] == "http://sds-federation-local-sync:8000/sync"


@pytest.mark.django_db
def test_sds_federation_well_known_explicit_overrides(client: Client, settings) -> None:
    settings.ADMIN_CONSOLE_ENV = "production"
    settings.SDS_SITE_FQDN = "sds.example.edu"
    settings.FEDERATION_SITE_NAME = "example"
    settings.SDS_SITE_DISPLAY_NAME = "Example"
    settings.FEDERATION_GATEWAY_API_BASE = "https://custom.example/api/v1"
    settings.FEDERATION_SYNC_SERVICE_URL = "https://custom.example/sync/"

    response = client.get(reverse("sds_federation_well_known"))

    payload = json.loads(response.content)
    assert payload["gateway_api_base"] == "https://custom.example/api/v1"
    assert payload["sync_service_url"] == "https://custom.example/sync/"


def test_resolve_well_known_fetch_url_local_self_site(settings) -> None:
    settings.ADMIN_CONSOLE_ENV = "local"
    settings.SDS_SITE_FQDN = "sds.localhost"
    settings.FEDERATION_REGISTRY_VERIFY_FETCH_BASE = ""

    assert (
        resolve_well_known_fetch_url("sds.localhost")
        == "http://sds-gateway-local-app:8000/.well-known/sds-federation.json"
    )
    assert (
        resolve_well_known_fetch_url("peer.example.edu")
        == "https://peer.example.edu/.well-known/sds-federation.json"
    )


def test_resolve_well_known_fetch_url_local_fetch_base_override(settings) -> None:
    settings.ADMIN_CONSOLE_ENV = "local"
    settings.SDS_SITE_FQDN = "sds.localhost"
    settings.FEDERATION_REGISTRY_VERIFY_FETCH_BASE = "http://custom-gateway:9000"

    assert (
        resolve_well_known_fetch_url("sds.localhost")
        == "http://custom-gateway:9000/.well-known/sds-federation.json"
    )


def test_resolve_well_known_fetch_url_production(settings) -> None:
    settings.ADMIN_CONSOLE_ENV = "production"
    settings.SDS_SITE_FQDN = "sds.example.edu"

    assert (
        resolve_well_known_fetch_url("sds.example.edu")
        == "https://sds.example.edu/.well-known/sds-federation.json"
    )


def test_build_sds_federation_document_includes_optional_registry_challenge(
    settings,
) -> None:
    settings.SDS_SITE_FQDN = "sds.crc.nd.edu"
    settings.FEDERATION_SITE_NAME = "crc"
    settings.FEDERATION_REGISTRY_CHALLENGE_TOKEN = "challenge-token"

    doc = build_sds_federation_document()

    assert doc["registry_challenge"] == "challenge-token"


@pytest.mark.django_db
def test_sds_federation_well_known_503_when_unconfigured(
    client: Client, settings
) -> None:
    settings.SDS_SITE_FQDN = ""
    settings.FEDERATION_SITE_NAME = ""
    settings.SDS_SITE_DISPLAY_NAME = ""

    response = client.get(reverse("sds_federation_well_known"))

    assert response.status_code == 503
