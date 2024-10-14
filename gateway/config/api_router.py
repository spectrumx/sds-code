from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from sds_gateway.api_methods.views.auth_endpoints import ValidateAuthViewSet
from sds_gateway.api_methods.views.file_endpoints import FileViewSet
from sds_gateway.users.api.views import UserViewSet

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet)
router.register(r"auth", ValidateAuthViewSet, basename="auth")
router.register(r"assets/files", FileViewSet, basename="files")

app_name = "api"
urlpatterns = router.urls
