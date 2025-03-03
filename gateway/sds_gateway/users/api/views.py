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

from sds_gateway.api_methods.models import KeySources
from sds_gateway.users.models import User
from sds_gateway.users.models import UserAPIKey

from .serializers import UserSerializer


@extend_schema(exclude=True)
class UserViewSet(
    RetrieveModelMixin,
    ListModelMixin,
    UpdateModelMixin,
    GenericViewSet[User],
):
    serializer_class = UserSerializer
    queryset: QuerySet[User, User] = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs) -> QuerySet[User, User]:
        assert isinstance(self.request.user.id, int), "User ID must be an integer"
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False)
    def me(self, request: HttpRequest) -> Response:
        """Get the current user's information."""
        user = cast(User, request.user)
        serializer = UserSerializer(user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


@extend_schema(exclude=True)
class GetAPIKeyView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]

    def get(self, request: Request) -> Response:
        """Generates an API Key for an SDS user."""

        log.debug(f"request.user: {request.user}")
        if request.user.email != settings.SVI_SERVER_EMAIL:
            return Response(
                {"error": "Unauthorized. Only SVI Server can access this endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )

        email = request.query_params.get("email")
        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            user = get_object_or_404(User, email=email, is_approved=True)
            UserAPIKey.objects.filter(user=user, source=KeySources.SVIBackend).delete()
            _, raw_key = UserAPIKey.objects.create_key(
                name=f"{user.email}-SVI-API-KEY",
                user=user,
                source=KeySources.SVIBackend,
            )
            return Response({"api_key": raw_key, "email": user.email})
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
