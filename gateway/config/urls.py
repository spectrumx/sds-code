from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include
from django.urls import path
from django.views import defaults as default_views
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from loguru import logger as log
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.permissions import AllowAny
from sds_gateway.users.views import home_page_view
from sds_gateway.users.views import spx_dac_dataset_alt_view

urlpatterns = [
    path("", home_page_view, name="home"),
    # Django Admin, use {% url 'admin:index' %}
    path(settings.ADMIN_URL, admin.site.urls),
    # User management
    path("users/", include("sds_gateway.users.urls", namespace="users")),
    path("accounts/", include("allauth.urls")),
    # SpectrumX DAC Dataset alternative download
    path("spx-dac/", spx_dac_dataset_alt_view, name="spx_dac_dataset_alt"),
    # Your stuff: custom urls includes go here
    # ...
    # Media files
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]

# Conditionally include visualizations
if settings.VISUALIZATIONS_ENABLED:
    urlpatterns += [
        path(
            "visualizations/",
            include("sds_gateway.visualizations.urls", namespace="visualizations"),
        ),
    ]
if settings.DEBUG:
    # Static file serving when using Gunicorn + Uvicorn for local web socket development
    urlpatterns += staticfiles_urlpatterns()

# API URLS
urlpatterns += [
    # API base url
    path(f"api/{settings.API_VERSION}/", include("config.api_router")),
    # redirect api/latest/ to api/<API_VERSION>/
    path("api/latest/", include("config.api_router")),
    # DRF auth token
    path(f"api/{settings.API_VERSION}/auth-token/", obtain_auth_token),
    path(
        f"api/{settings.API_VERSION}/schema/",
        SpectacularAPIView.as_view(
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="api-schema",
    ),
    path(
        f"api/{settings.API_VERSION}/docs/",
        SpectacularSwaggerView.as_view(
            template_name="swagger-ui.html",
            url_name="api-schema",
            permission_classes=[AllowAny],
            authentication_classes=[],
        ),
        name="api-docs",
    ),
]

if settings.DEBUG:
    # This allows the error pages to be debugged during development, just visit
    # these url in browser to see how these error pages look like.
    urlpatterns += [
        path(
            "400/",
            default_views.bad_request,
            kwargs={"exception": Exception("Bad Request!")},
        ),
        path(
            "403/",
            default_views.permission_denied,
            kwargs={"exception": Exception("Permission Denied")},
        ),
        path(
            "404/",
            default_views.page_not_found,
            kwargs={"exception": Exception("Page not Found")},
        ),
        path("500/", default_views.server_error),
    ]
    if "debug_toolbar" in settings.INSTALLED_APPS:
        try:
            import debug_toolbar  # pyright: ignore[reportMissingImports]

            urlpatterns = [
                path("__debug__/", include(debug_toolbar.urls)),
                *urlpatterns,
            ]
        except ImportError:
            log.warning(
                "debug_toolbar is listed in installed apps but could not be imported",
            )
