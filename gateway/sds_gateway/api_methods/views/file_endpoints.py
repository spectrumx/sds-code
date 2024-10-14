import datetime

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.api_methods.views.auth_endpoints import APIKeyAuthentication


class FileViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=FilePostSerializer,
        responses={
            201: FilePostSerializer,
            400: "Bad Request",
        },
        description="Upload a file to the server.",
        summary="Upload File",
    )
    def create(self, request, *args, **kwargs):
        serializer = FilePostSerializer(
            data=request.data,
            context={"request_user": request.user},
        )
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            200: FileGetSerializer,
            404: "Not Found",
        },
        description="Retrieve a file from the server.",
        summary="Retrieve File",
    )
    def retrieve(self, request, pk=None):
        file = get_object_or_404(File, pk=pk, owner=request.user)
        serializer = FileGetSerializer(file, many=False)
        return Response(serializer.data)

    @extend_schema(
        responses={
            200: FileGetSerializer,
            404: "Not Found",
        },
        description="Retrieve the most recent file uploaded by the user.",
        summary="Retrieve Most Recent File",
        parameters=[
            OpenApiParameter(
                name="path",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="The directory path to retrieve latest file from.",
            ),
        ],
    )
    def list(self, request):
        # get query params included in request and filter queryset
        path = request.GET.get("path")
        if not path:
            return Response(
                {"detail": "Path parameter is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # get the most recent file
        most_recent_file = (
            File.objects.filter(
                owner=request.user,
                is_deleted=False,
                directory=path,
            )
            .order_by("-created_at")
            .first()
        )
        serializer = FileGetSerializer(most_recent_file, many=False)

        return Response(serializer.data)

    @extend_schema(
        request=FilePostSerializer,
        responses={
            200: FilePostSerializer,
            400: "Bad Request",
            404: "Not Found",
        },
        description="Update a file on the server.",
        summary="Update File",
    )
    def update(self, request, pk=None):
        file = get_object_or_404(File, pk=pk, owner=request.user)
        serializer = FilePostSerializer(file, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        responses={
            204: "No Content",
            404: "Not Found",
        },
        description="Delete a file from the server.",
        summary="Delete File",
    )
    def destroy(self, request, pk=None):
        file = get_object_or_404(File, pk=pk, owner=request.user)
        file.is_deleted = True
        file.deleted_at = datetime.datetime.now(datetime.UTC)
        file.save()

        # return status for soft deletion
        return Response(status=status.HTTP_204_NO_CONTENT)
