import datetime

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

import sds_gateway.api_methods.utils.swagger_example_schema as example_schema
from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import (
    FileCheckResponseSerializer,
)
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer


class FileViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=FilePostSerializer,
        responses={
            201: FilePostSerializer,
            400: OpenApiResponse(description="Bad Request"),
            409: OpenApiResponse(description="Conflict"),
        },
        examples=[
            OpenApiExample(
                "Example File Post Request",
                summary="File Request Body",
                description="This is an example of a file post request body.",
                value=example_schema.file_post_request_example_schema,
                request_only=True,
            ),
            OpenApiExample(
                "Example File Post Response",
                summary="File Post Response Body",
                description="This is an example of a file post response body.",
                value=example_schema.file_post_response_example_schema,
                response_only=True,
            ),
        ],
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
        parameters=[
            OpenApiParameter(
                name="id",
                description="File UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: FileGetSerializer,
            404: OpenApiResponse(description="Not Found"),
        },
        examples=[
            OpenApiExample(
                "Example File Get Response",
                summary="File Get Response Body",
                description="This is an example of a file get response body.",
                value=example_schema.file_get_response_example_schema,
                response_only=True,
            ),
        ],
        description="Retrieve a file from the server.",
        summary="Retrieve File",
    )
    def retrieve(self, request, pk=None):
        file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )
        serializer = FileGetSerializer(file, many=False)
        return Response(serializer.data)

    @extend_schema(
        responses={
            200: FileGetSerializer,
            404: OpenApiResponse(description="Not Found"),
        },
        examples=[
            OpenApiExample(
                "Example File Get Response",
                summary="File Get Response Body",
                description="This is an example of a file get response body.",
                value=example_schema.file_get_response_example_schema,
                response_only=True,
            ),
        ],
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
        parameters=[
            OpenApiParameter(
                name="id",
                description="File UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        examples=[
            OpenApiExample(
                "Example File Put Request",
                summary="File Put Request Body",
                description="This is an example of a file put request body.",
                value=example_schema.file_put_request_example_schema,
                request_only=True,
            ),
            OpenApiExample(
                "Example File Put Response",
                summary="File Put Response Body",
                description="This is an example of a file put response body.",
                value=example_schema.file_post_response_example_schema,
                response_only=True,
            ),
        ],
        request=FilePostSerializer,
        responses={
            200: FilePostSerializer,
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
        description="Update a file on the server.",
        summary="Update File",
    )
    def update(self, request, pk=None):
        file = get_object_or_404(File, pk=pk, owner=request.user, is_deleted=False)

        directory = request.data.get("directory", None)
        if directory and not directory.startswith(f"/files/{request.user.email}"):
            return Response(
                {
                    "detail": f"The directory must include the user file path: /files/{request.user.email}/",  # noqa: E501
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FilePostSerializer(file, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="File UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            204: OpenApiResponse(description="No Content"),
            404: OpenApiResponse(description="Not Found"),
        },
        description="Delete a file from the server.",
        summary="Delete File",
    )
    def destroy(self, request, pk=None):
        file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )
        file.is_deleted = True
        file.deleted_at = datetime.datetime.now(datetime.UTC)
        file.save()

        # return status for soft deletion
        return Response(status=status.HTTP_204_NO_CONTENT)


class CheckFileContentsExistView(APIView):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=FilePostSerializer,
        responses={
            200: FileCheckResponseSerializer,
            400: OpenApiResponse(description="Bad Request"),
        },
        examples=[
            OpenApiExample(
                "Example File Contents Check Request",
                summary="File Contents Check Request Body",
                description="This is an example of a file contents check request body.",
                value=example_schema.file_contents_check_request_example_schema,
                request_only=True,
            ),
        ],
        description="Check if the file contents exist on the server.",
        summary="Check File Contents Exist",
    )
    def post(self, request):
        user = request.user
        file = request.FILES["file"]
        if not file:
            return Response(
                {"detail": "No file provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        directory = request.data.get("directory", None)
        if not directory:
            return Response(
                {"detail": "No directory provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not directory.startswith(f"/files/{request.user.email}"):
            directory = f"/files/{request.user.email}/{directory}/"
            request.data["directory"] = directory

        name = file.name
        checksum = File().calculate_checksum(file)
        serializer = FilePostSerializer()
        conditions = serializer.check_file_conditions(
            user,
            directory,
            name,
            checksum,
            request.data,
        )
        return Response(conditions, status=status.HTTP_200_OK)


check_contents_exist = CheckFileContentsExistView.as_view()
