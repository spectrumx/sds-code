from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.authentication import APIKeyAuthentication


class ValidateAuthViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]

    @extend_schema(
        responses={
            200: OpenApiResponse(description="API key is valid for <user.email>"),
            403: OpenApiResponse(description="Forbidden"),
        },
        description="Validate the API key.",
        summary="Validate API Key",
    )
    def list(self, request):
        user, _ = APIKeyAuthentication().authenticate(request)
        return Response(
            {"message": f"API key is valid for {user.email}"},
            status=status.HTTP_200_OK,
        )
