from django.urls import path

from .views import WaterfallVisualizationView

app_name = "visualizations"

urlpatterns = [
    path(
        "waterfall/<str:capture_uuid>/",
        WaterfallVisualizationView.as_view(),
        name="waterfall",
    ),
]
