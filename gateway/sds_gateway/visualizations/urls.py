from django.conf import settings
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
]

# Add spectrogram URLs only if experimental feature is enabled
if settings.EXPERIMENTAL_SPECTROGRAM:
    template_urlpatterns.append(
        path(
            "spectrogram/<str:capture_uuid>/",
            SpectrogramVisualizationView.as_view(),
            name="spectrogram",
        )
    )

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
]

# Add spectrogram API URLs only if experimental feature is enabled
if settings.EXPERIMENTAL_SPECTROGRAM:
    api_urlpatterns.extend(
        [
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
        ]
    )

urlpatterns = template_urlpatterns + api_urlpatterns
