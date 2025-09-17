from django.urls import path

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

urlpatterns = template_urlpatterns
