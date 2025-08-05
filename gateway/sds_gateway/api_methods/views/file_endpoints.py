"""File operations endpoints for the SDS Gateway API."""

from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

from django.db.models import CharField
from django.db.models import F as FExpression
from django.db.models import Value as WrappedValue
from django.db.models.functions import Concat
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from loguru import logger as log
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

import sds_gateway.api_methods.utils.swagger_example_schema as example_schema
from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.download_file import download_file
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.serializers.file_serializers import (
    FileCheckResponseSerializer,
)
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FilePostSerializer
from sds_gateway.api_methods.utils.sds_files import sanitize_path_rel_to_user

# Custom status code for client closed request
HTTP_499_CLIENT_CLOSED_REQUEST = 499

if TYPE_CHECKING:
    from django.http.request import QueryDict

    from sds_gateway.users.models import User


class FilePagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class FileViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def _is_client_disconnected(self, request):
        """Check if the client has disconnected from the request."""
        try:
            # Check if the request is still connected
            if hasattr(request, "_closed") and getattr(request, "_closed", False):
                log.info("Client disconnected: request._closed is True")
                return True
            # Try to access request body to see if connection is still alive
            if hasattr(request, "body"):
                # This will raise an exception if the client disconnected
                _ = request.body
            log.info("Client disconnection check passed")
        except (ConnectionError, OSError) as e:
            log.info("Client disconnected: exception caught: %s", e)
            return True
        else:
            return False

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
                value=example_schema.file_post_request_example_schema,
                request_only=True,
            ),
            OpenApiExample(
                "Example File Post Response",
                summary="File Post Response Body",
                value=example_schema.file_post_response_example_schema,
                response_only=True,
            ),
        ],
        summary="Upload File",
    )
    def create(self, request: Request) -> Response:
        """Uploads a file to the server."""

        # Check for client disconnection
        if self._is_client_disconnected(request):
            log.info("Client disconnected in FileViewSet.create")
            return Response(
                {"detail": "Client disconnected"},
                status=HTTP_499_CLIENT_CLOSED_REQUEST,
            )

        # when a sibling file is provided, use its file contents
        if sibling_uuid := request.data.get("sibling_uuid"):
            log.info(f"Sibling file upload request: '{sibling_uuid}'")
            # .copy() only works for this mode
            request_data = request.data.copy()
            request_data["owner"] = request.user.pk
            sibling_file = get_object_or_404(
                File,
                uuid=sibling_uuid,
                owner=request.user,
                is_deleted=False,
            )
            keys_to_remove = ["sibling_uuid", "sum_blake3", "file", "owner"]
            for key in keys_to_remove:
                request_data.pop(key, None)
            request_data.update(
                file=sibling_file.file,
                sum_blake3=sibling_file.sum_blake3,
                owner=request.user.pk,
            )
            serializer = FilePostSerializer(
                data=request_data,
                context={"request_user": request.user},
            )
        else:
            log.debug("Original file upload request")
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
        user_dir = f"/files/{request.user.email}"
        if serializer.is_valid(raise_exception=False):
            serializer.save()
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
        log.warning(f"File upload 400: {serializer.errors}")
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
                value=example_schema.file_list_response_example_schema,
                response_only=True,
            ),
        ],
        description="Retrieve a file from the server.",
        summary="Retrieve File",
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        if pk is None:
            return Response(
                {"detail": "File UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )
        serializer = FileGetSerializer(target_file, many=False)
        return Response(serializer.data)

    @extend_schema(
        responses={
            200: FileGetSerializer,
            404: OpenApiResponse(description="Not Found"),
        },
        examples=[
            OpenApiExample(
                "Example of File Listing Response",
                summary="File Listing Response Body",
                value=example_schema.file_list_response_example_schema,
                response_only=True,
            ),
        ],
        summary="Lists files",
        parameters=[
            OpenApiParameter(
                name="path",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "The first part of the path to retrieve files from, "
                    "or an exact file match (directory + name)."
                ),
            ),
            OpenApiParameter(
                name="page",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Page number for pagination.",
                default=1,
            ),
            OpenApiParameter(
                name="page_size",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Number of items per page.",
                default=FilePagination.page_size,
            ),
        ],
    )
    def list(self, request: Request) -> Response:
        """
        Lists all files owned by the user. When `path` is passed, it filters all
            files matching that subdirectory. If `path` is an exact file path
            (directory + name) with multiple matches (versions), it will retrieve the
            most recent one that matches that path. Wildcards are not yet supported.
        """
        unsafe_path = request.GET.get("path", "/").strip()
        basename = Path(unsafe_path).name

        user_rel_path = sanitize_path_rel_to_user(
            unsafe_path=unsafe_path,
            request=request,
        )
        log.debug(f"Listing for '{user_rel_path}'")
        if user_rel_path is None:
            return Response(
                {"detail": "The provided path must be in the user's files directory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        all_valid_user_owned_files = File.objects.filter(
            owner=request.user,
            is_deleted=False,
        )

        paginator = FilePagination()

        # if we could extract a basename, try an exact match first
        if basename:
            inferred_user_rel_path = user_rel_path.parent
            exact_match_query = all_valid_user_owned_files.filter(
                name=basename,
                directory__in=[
                    str(inferred_user_rel_path),
                    str(inferred_user_rel_path) + "/",
                ],
            ).order_by(
                "-created_at",
            )[
                :1  # replace this when allowing listing multiple file versions
            ]
            if exact_match_query.exists():
                paginated_files = paginator.paginate_queryset(
                    exact_match_query,
                    request=request,
                )
                serializer = FileGetSerializer(paginated_files, many=True)

                # despite being a single result, we return it paginated for consistency
                return paginator.get_paginated_response(serializer.data)

            log.debug(
                "No exact match found for "
                f"{inferred_user_rel_path!s} and name {basename}",
            )

        # try matching `directory`, ignoring `name`
        files_matching_dir = all_valid_user_owned_files.filter(
            directory__startswith=str(user_rel_path),
        )

        files_matching_dir = files_matching_dir.annotate(
            path=Concat(
                FExpression("directory"),
                WrappedValue("/"),
                FExpression("name"),
                output_field=CharField(),
            ),
        )

        # get the latest file for each directory + name combination
        latest_files = files_matching_dir.order_by("path", "-created_at").distinct(
            "path",
        )

        paginated_files = paginator.paginate_queryset(latest_files, request=request)
        serializer = FileGetSerializer(paginated_files, many=True)

        first_file = all_valid_user_owned_files.first()
        if first_file:
            log.debug(f"First file directory: {first_file.directory}")
            log.debug(f"First file name: {first_file.name}")

        log.debug(
            f"Matched {latest_files.count()} / {all_valid_user_owned_files.count()} "
            f"user files for path {user_rel_path!s} - returning {len(serializer.data)}",
        )

        return paginator.get_paginated_response(serializer.data)

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
                value=example_schema.example_file_update_request,
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
    def update(self, request: Request, pk: str | None = None) -> Response:
        """Updates a file (metadata-only) on the server."""
        if pk is None:
            return Response(
                {"detail": "File UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        unsafe_path = request.data.get("directory", None)
        if unsafe_path is None:
            return Response(
                {"detail": "No directory provided."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user_rel_path = sanitize_path_rel_to_user(
            unsafe_path=unsafe_path,
            request=request,
        )
        if user_rel_path is None:
            return Response(
                {"detail": "The provided path must be in the user's files directory."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request_data = request.data.copy()
        request_data["directory"] = str(user_rel_path)

        serializer = FilePostSerializer(target_file, data=request_data, partial=True)
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
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Soft deletes a file from the server."""
        if pk is None:
            return Response(
                {"detail": "File UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )
        target_file.soft_delete()

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
            500: OpenApiResponse(
                description="Internal Server Error - File download failed"
            ),
        },
        description=(
            "Download a file from the server. Returns the file content as an HTTP "
            "response with appropriate headers."
        ),
        summary="Download File",
    )
    @action(detail=True, methods=["get"], url_path="download", url_name="download")
    def download_file(self, request: Request, pk: str | None = None) -> HttpResponse:
        """Downloads a file from the server."""
        if pk is None:
            return Response(
                {"detail": "File UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_file = get_object_or_404(
            File,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        try:
            # Use the helper function to download the file
            file_content = download_file(target_file)

            # Create HTTP response with the file content
            http_response = HttpResponse(
                file_content,
                content_type=target_file.media_type,
            )
            http_response["Content-Disposition"] = (
                f'attachment; filename="{target_file.name}"'
            )

        except (OSError, ValueError):
            log.exception("Error downloading file %s", target_file.name)
            return Response(
                {"detail": "Failed to download file"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        else:
            return http_response


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
                value=example_schema.example_file_content_check_request,
                request_only=True,
            ),
        ],
        description="Check if the file contents exist on the server.",
        summary="Check File Contents Exist",
    )
    def post(self, request: Request) -> Response:
        """Checks if the file contents in request metadata exist on the server.

        Used to prevent unnecessary file uploads when the file contents already exist.

        Response payload:
            file_exists_in_tree: True when the contents checksum, directory, and name
                match an existing file in the user's files directory. Meaning a content
                upload is unnecessary and the file may be referenced by its path (dir + name).
            file_contents_exist_for_user: True when the user has a file with the
                same checksum, regardless of directory or name. Meaning content
                upload is unnecessary.
            user_mutable_attributes_differ: True when the file doesn't exist, or the
                matching file's attributes (e.g. media_type, permissions) differ
                from the request metadata. Meaning a metadata update is necessary
                to create a full match.
            asset_id: The ID of the "best-match" file in the following order or availability:
                1. File with same contents, directory, and name (when file_exists_in_tree=True)
                    Note their metadata may still differ.
                2. File with same contents (when file_contents_exist_for_user=True)
                3. None (when no match is found)

        Example request data:
            {
                "metadata": {
                    "directory": "/path/to/file",
                    "name": "file.h5",
                    "sum_blake3": "55c6dac98fbc9a388f619f5f4ffc4c9fdd3eb37eab48afd68b65da90ef3070b1",
                }
            }
        Example response:
            {
                "file_exists_in_tree": False,
                "file_contents_exist_for_user": True,
                "user_mutable_attributes_differ": True,
                "asset_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            }
        In that example response, an exact match was not found, but another file with
            same contents was found (a sibling file). Thus, a file *content* upload is not
            necessary. The asset ID points to this sibling file, which can be used in place
            of the file contents when creating a new file.
        In cases when an "exact" match exists (contents + directory + name) - indicated by
            `file_exists_in_tree` being True - `asset_id` will point to this matched entry.
        Note that a check that gives file_exists_in_tree=True may still have diverging metadata
            such as permissions. That is indicated by `user_mutable_attributes_differ`
            being True, which can be used to trigger a metadata update.
        """  # noqa: E501
        user = cast("User", request.user)
        request_data = cast("QueryDict", request.data)

        unsafe_path = request_data.get("directory")
        if not unsafe_path:
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
        user_rel_path = sanitize_path_rel_to_user(
            unsafe_path=unsafe_path,
            request=request,
        )
        if user_rel_path is None:
            return Response(
                {"detail": "The provided path must be in the user's files directory."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = FilePostSerializer()
        conditions = serializer.check_file_contents_exist(
            blake3_sum=checksum_from_client,
            directory=str(user_rel_path),
            name=file_name_from_client,
            request_data=request_data,
            user=user,
        )
        return Response(conditions, status=status.HTTP_200_OK)


check_contents_exist = CheckFileContentsExistView.as_view()
