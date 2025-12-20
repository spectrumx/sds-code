from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter
from sds_gateway.api_methods.views.auth_endpoints import ValidateAuthViewSet
from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet
from sds_gateway.api_methods.views.dataset_endpoints import DatasetViewSet
from sds_gateway.api_methods.views.file_endpoints import FileViewSet
from sds_gateway.api_methods.views.file_endpoints import check_contents_exist
from sds_gateway.users.api.views import UserViewSet
from sds_gateway.visualizations.api_views import VisualizationViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register(r"auth", ValidateAuthViewSet, basename="auth")
router.register(r"assets/files", FileViewSet, basename="files")
router.register(r"assets/captures", CaptureViewSet, basename="captures")
router.register(r"assets/datasets", DatasetViewSet, basename="datasets")

if settings.VISUALIZATIONS_ENABLED:
    router.register(r"visualizations", VisualizationViewSet, basename="visualizations")

app_name = "api"
urlpatterns = [
    *router.urls,
    path(
        "assets/utils/check_contents_exist/",
        check_contents_exist,
        name="check_contents_exist",
    ),
]
