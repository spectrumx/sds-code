from config.settings.utils import guess_admin_console_env
from django.template.loader import render_to_string
from django.test import RequestFactory

from sds_gateway.context_processors import app_settings


def test_app_settings_exposes_admin_console_env(settings, rf: RequestFactory) -> None:
    settings.ADMIN_CONSOLE_ENV = "staging"
    request = rf.get("/")

    context = app_settings(request)

    assert context["ADMIN_CONSOLE_ENV"] == "staging"
    assert "VISUALIZATIONS_ENABLED" in context


def test_guess_admin_console_env_for_staging(monkeypatch) -> None:
    monkeypatch.setattr(
        "config.settings.utils.gethostname", lambda: "sds-gateway-staging-app"
    )

    environment = guess_admin_console_env(is_debug=False)

    assert environment == "staging"


def test_guess_admin_console_env_for_local_debug(monkeypatch) -> None:
    monkeypatch.setattr(
        "config.settings.utils.gethostname", lambda: "sds-gateway-prod-app"
    )

    environment = guess_admin_console_env(is_debug=True)

    assert environment == "local"


def test_guess_admin_console_env_for_production(monkeypatch) -> None:
    monkeypatch.setattr(
        "config.settings.utils.gethostname", lambda: "sds-gateway-prod-app"
    )

    environment = guess_admin_console_env(is_debug=False)

    assert environment == "production"


def test_admin_template_shows_environment_and_fqdn(
    settings,
    rf: RequestFactory,
) -> None:
    settings.ADMIN_CONSOLE_ENV = "staging"
    settings.SDS_SITE_FQDN = "staging.sds.example"
    request = rf.get("/admin/")

    rendered = render_to_string("admin/base_site.html", request=request)

    assert "Django Administration" in rendered
    assert "staging" in rendered.lower()
    assert "staging.sds.example" in rendered.lower()
