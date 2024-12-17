"""File operations endpoints for the SDS Gateway API."""

import datetime
import logging
from pathlib import Path
from typing import cast

from django.conf import settings
from django.http import HttpResponse
from django.http.request import QueryDict
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
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
from sds_gateway.api_methods.utils.minio_client import get_minio_client
from sds_gateway.users.models import User


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
    def create(self, request, *args, **kwargs) -> Response:
        """Receives a file from the user request and saves it to the server."""

        serializer = FilePostSerializer(
            data=request.data,
            context={"request_user": request.user},
        )
        attrs_to_return = [
            "uuid",
            "name",
            "directory",
            "media_type",
            "size",
            "sum_blake3",
            "created_at",
            "updated_at",
            "permissions",
            "expiration_date",
        ]
        logging.debug("Validating file upload: %s", serializer)
        user_dir = f"/files/{request.user.email}"
        if serializer.is_valid(raise_exception=True):
            serializer.save()
            logging.debug("New file uploaded: %s", serializer["uuid"])
            returned_object = {}
            for key, value in serializer.data.items():
                if key not in attrs_to_return:
                    continue
                if key == "directory":
                    # return path with user_dir as the "root"
                    rel_path = str(Path(value).relative_to(user_dir))
                    returned_object[key] = str(Path("/" + rel_path))
                else:
                    returned_object[key] = value
            return Response(returned_object, status=status.HTTP_201_CREATED)
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
        user_files_dir = f"/files/{request.user.email}"

        if directory:
            # Resolve the top_level_dir to an absolute path
            resolved_dir = Path(directory).resolve(strict=False)

            # Ensure the resolved path is within the user's files directory
            user_files_dir = Path(user_files_dir).resolve(strict=False)
            if not resolved_dir.is_relative_to(user_files_dir):
                msg = f"The provided directory must be in the user's files directory: {user_files_dir}"  # noqa: E501
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

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

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="File UUID",
                required=True,
                type=str,
            ),
        ],
        responses={
            200: OpenApiResponse(description="HTTP File Response"),
            404: OpenApiResponse(description="Not Found"),
            500: OpenApiResponse(description="Internal Server Error"),
        },
        description="Download a file from the server.",
        summary="Download File",
    )
    @action(detail=True, methods=["get"], url_path="download", url_name="download")
    def download_file(self, request, pk=None):
        file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        client = get_minio_client()

        minio_response = None
        try:
            # Get the file content from MinIO
            minio_response = client.get_object(
                settings.AWS_STORAGE_BUCKET_NAME,
                file.file.name,
            )

            # Read the file content into memory
            file_content = minio_response.read()

            # Serve the file content as a response
            http_response = HttpResponse(
                file_content,
                content_type=file.media_type,
            )
            http_response["Content-Disposition"] = f'attachment; filename="{file.name}"'
        except client.exceptions.NoSuchKey as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except client.exceptions.ResponseError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        else:
            return http_response
        finally:
            # if there was a response, close it and release the connection
            if minio_response:
                minio_response.close()
                minio_response.release_conn()


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
    def post(self, request: Request) -> Response:
        """Checks if the file contents in request metadata exist on the server.

        Used o prevent unnecessary file uploads when the file contents already exist.

        Response flags:
            file_exists_in_tree: True when the file checksum, directory, and name
                match an existing file in the user's files directory. Meaning any
                upload or update is unnecessary.
            file_contents_exist_for_user: True when the user has a file with the
                same checksum, regardless of directory or name. Meaning content
                upload is unnecessary.
            user_mutable_attributes_differ: True when the file doesn't exist, or the
                matching file's attributes (e.g. media_type, permissions) differ
                from the request metadata. Meaning a metadata update is necessary.

        Example request data:
            {
                "metadata": {
                    "directory": "/path/to/file",
                    "name": "file.h5",
                    "sum_blake3": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                }
            }
        Example response:
            {
                "file_exists_in_tree": False,
                "file_contents_exist_for_user": True,
                "user_mutable_attributes_differ": False,
            }
        """
        user = cast(User, request.user)
        request_data = cast(QueryDict, request.data)

        file_dir_from_client = request_data.get("directory")
        if not file_dir_from_client:
            return Response(
                {"detail": "No directory provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        checksum_from_client = request_data.get("sum_blake3")
        if not checksum_from_client:
            return Response(
                {"detail": "No checksum provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_name_from_client = request_data.get("name")
        if not file_name_from_client:
            return Response(
                {"detail": "No file name provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ensure the resolved path is within the user's files directory
        user_root_dir = Path("/files/") / user.email
        if Path(file_dir_from_client).is_absolute():
            file_dir_from_client = Path(f"./{file_dir_from_client}")
        user_relative_dir = user_root_dir / file_dir_from_client
        resolved_dir = Path(user_relative_dir).resolve(strict=False)
        if not resolved_dir.is_relative_to(user_root_dir):
            msg = (
                "The provided directory must be in the user's files directory: "
                f"'{file_dir_from_client}' should be under '{user_root_dir}'"
            )
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        serializer = FilePostSerializer()
        conditions = serializer.check_file_contents_exist(
            blake3_sum=checksum_from_client,
            directory=str(file_dir_from_client),
            name=file_name_from_client,
            request_data=request.data,
            user=user,
        )
        return Response(conditions, status=status.HTTP_200_OK)


check_contents_exist = CheckFileContentsExistView.as_view()
