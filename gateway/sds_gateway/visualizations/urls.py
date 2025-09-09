from django.urls import path

from .api_views import VisualizationViewSet
from .views import SpectrogramVisualizationView
from .views import WaterfallVisualizationView

app_name = "visualizations"

# Template view URLs (for displaying visualizations)
template_urlpatterns = [
    path(
        "waterfall/<str:capture_uuid>/",
        WaterfallVisualizationView.as_view(),
        name="waterfall",
    ),
    path(
        "spectrogram/<str:capture_uuid>/",
        SpectrogramVisualizationView.as_view(),
        name="spectrogram",
    ),
]

# API view URLs (for programmatic access)
api_urlpatterns = [
    path(
        "api/",
        VisualizationViewSet.as_view(
            {
                "get": "get_visualization_compatibility",
            }
        ),
        name="api_compatibility",
    ),
    path(
        "api/<str:capture_uuid>/",
        VisualizationViewSet.as_view(
            {
                "post": "create_spectrogram",
                "get": "get_spectrogram_status",
            }
        ),
        name="api_spectrogram",
    ),
    path(
        "api/<str:capture_uuid>/download/",
        VisualizationViewSet.as_view(
            {
                "get": "download_spectrogram",
            }
        ),
        name="api_download_spectrogram",
    ),
    path(
        "api/<str:capture_uuid>/create_waterfall/",
        VisualizationViewSet.as_view(
            {
                "post": "create_waterfall",
            }
        ),
        name="api_create_waterfall",
    ),
    path(
        "api/<str:capture_uuid>/waterfall_status/",
        VisualizationViewSet.as_view(
            {
                "get": "get_waterfall_status",
            }
        ),
        name="api_waterfall_status",
    ),
    path(
        "api/<str:capture_uuid>/download_waterfall/",
        VisualizationViewSet.as_view(
            {
                "get": "download_waterfall",
            }
        ),
        name="api_download_waterfall",
    ),
    path(
        "api/<str:capture_uuid>/download_waterfall_low_res/",
        VisualizationViewSet.as_view(
            {
                "get": "download_waterfall_low_res",
            }
        ),
        name="api_download_waterfall_low_res",
    ),
]

urlpatterns = template_urlpatterns + api_urlpatterns
