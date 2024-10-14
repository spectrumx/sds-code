import logging

from django.contrib.auth import get_user_model
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.users.models import UserAPIKey

User = get_user_model()
logger = logging.getLogger(__name__)


class APIKeyAuthentication(BaseAuthentication):
    def authenticate(self, request):
        api_key = request.headers.get("Authorization")
        if not api_key:
            msg = "No API key provided"
            logger.exception(msg)
            raise AuthenticationFailed(msg)

        try:
            api_key = api_key.split(" ")[1]
            api_key_obj = UserAPIKey.objects.get_from_key(api_key)
        except (UserAPIKey.DoesNotExist, IndexError) as err:
            msg = "Invalid API key"
            logger.exception(msg)
            raise AuthenticationFailed(msg) from err

        user = api_key_obj.user
        return (user, True)


class ValidateAuthViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]

    @extend_schema(
        responses={
            200: "API key is valid for `user.email`",
            403: "Forbidden",
        },
        description="Validate the API key.",
        summary="Validate API Key",
        parameters=[
            OpenApiParameter(
                name="Authorization",
                location=OpenApiParameter.HEADER,
                type=OpenApiTypes.STR,
                description="API key in the format `Api-Key YOUR_API_KEY`",
            ),
        ],
    )
    def list(self, request):
        user, _ = APIKeyAuthentication().authenticate(request)
        return Response(
            {"message": f"API key is valid for {user.email}"},
            status=status.HTTP_200_OK,
        )
