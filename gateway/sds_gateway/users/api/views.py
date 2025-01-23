from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.conf import settings
from rest_framework.views import APIView

from sds_gateway.users.models import User

from .serializers import UserSerializer


class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "pk"

    def get_queryset(self, *args, **kwargs):
        assert isinstance(self.request.user.id, int)
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False)
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)


class GetAPIKeyView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Verify the requesting user is the SVI Server
        if request.user.email != settings.SVI_SERVER_EMAIL:
            return Response(
                {"error": "Unauthorized. Only SVI Server can access this endpoint."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Get email from query parameters
        email = request.query_params.get('email')
        if not email:
            return Response(
                {"error": "Email is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Look up user by email
        try:
            user = get_object_or_404(User, email=email)
            return Response({
                "api_key": user.get_svi_api_key(),
                "email": user.email
            })
        except User.DoesNotExist:
            return Response(
                {"error": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )