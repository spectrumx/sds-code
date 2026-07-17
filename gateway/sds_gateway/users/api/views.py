from collections.abc import Callable
from typing import cast

from django.conf import settings
from django.db.models import QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from loguru import logger as log
from rest_framework import status
from rest_framework.authentication import TokenAuthentication
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import GenericViewSet

from sds_gateway.users.backend_service_key_utils import mint_federation_sync_api_key
from sds_gateway.users.backend_service_key_utils import mint_svi_backend_api_key
from sds_gateway.users.models import User

from .serializers import UserSerializer

class ServiceUserSetting(StrEnum):
    SVI_SERVER_EMAIL = "SVI_SERVER_EMAIL"
    FEDERATION_SYNC_USER_EMAIL = "FEDERATION_SYNC_USER_EMAIL"


@extend_schema(exclude=True)
class UserViewSet(
    RetrieveModelMixin,
    ListModelMixin,
    UpdateModelMixin,
    GenericViewSet[User],
):
    serializer_class = UserSerializer
    queryset: QuerySet[User] = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs) -> QuerySet[User]:
        assert isinstance(self.request.user.id, int), "User ID must be an integer"
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False)
    def me(self, request: HttpRequest) -> Response:
        """Get the current user's information."""
        user = cast("User", request.user)
        serializer = UserSerializer(user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


@extend_schema(exclude=True)
class BackendServiceMintAPIKeyView(APIView):
    """Token-authenticated mint endpoint for internal backend services."""

    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    service_user_email_setting = ""
    unauthorized_message = ""
    mint_user_api_key: Callable[[User], str] | None = None

    def get(self, request: Request) -> Response:
        allowed_email = getattr(settings, self.service_user_email_setting)
        
        if not request.user.is_authenticated:
            return Response(
                {"error": "The requesting user could not be identified."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        request_email = request.user.email
        if request_email != allowed_email:
            return Response(
                {"error": self.unauthorized_message},
                status=status.HTTP_403_FORBIDDEN,
            )

        email_to_mint = ""
        if self.service_user_email_setting == ServiceUserSetting.FEDERATION_SYNC_USER_EMAIL:
            email_to_mint = request_email
        elif self.service_user_email_setting == ServiceUserSetting.SVI_SERVER_EMAIL:
            email_to_mint = request.query_params.get("email")
            if not email_to_mint:
                return Response(
                    {"error": "Email parameter is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        user = get_object_or_404(User, email=email_to_mint, is_approved=True)
        raw_key = self.mint_user_api_key(user)
        return Response({"api_key": raw_key, "email": user.email})


get_svi_api_key_view = BackendServiceMintAPIKeyView.as_view(
    service_user_email_setting=ServiceUserSetting.SVI_SERVER_EMAIL,
    unauthorized_message="Unauthorized. Only SVI Server can access this endpoint.",
    mint_user_api_key=mint_svi_backend_api_key,
)

get_federation_sync_api_key_view = BackendServiceMintAPIKeyView.as_view(
    service_user_email_setting=ServiceUserSetting.FEDERATION_SYNC_USER_EMAIL,
    unauthorized_message=(
        "Unauthorized. Only federation sync can access this endpoint."
    ),
    mint_user_api_key=mint_federation_sync_api_key,
)
