import tempfile
from pathlib import Path
from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from opensearchpy import exceptions as os_exceptions
from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

import sds_gateway.api_methods.utils.swagger_example_schema as example_schema
from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.extract_drf_metadata import (
    validate_metadata_by_channel,
)
from sds_gateway.api_methods.helpers.index_handling import index_capture_metadata
from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.capture_serializers import (
    CaptureGetSerializer,
    CapturePostSerializer,
)
from sds_gateway.users.models import User


class CaptureViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    @extend_schema(
        request=CapturePostSerializer,
        responses={
            201: CaptureGetSerializer,
            400: OpenApiResponse(description="Bad Request"),
        },
        examples=[
            OpenApiExample(
                "Example Capture Request",
                summary="Capture Request Body",
                value=example_schema.capture_request_example_schema,
                request_only=True,
            ),
            OpenApiExample(
                "Example Capture Response",
                summary="Capture Response Body",
                value=example_schema.capture_response_example_schema,
                response_only=True,
            ),
        ],
        description="Create a capture object, connect files to the capture, and index its metadata.",  # noqa: E501
        summary="Create Capture",
    )
    def create(self, request: Request) -> Response:
        # channel whose data/metadata to capture
        channel = request.data.get("channel", None)
        # path to directory that contains the channel dirs
        requested_top_level_dir = Path(request.data.get("top_level_dir", ""))
        requester = cast(User, request.user)

        # Ensure the top_level_dir is not a relative path
        if not requested_top_level_dir.is_absolute():
            msg = "Relative paths are not allowed."
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # Resolve the top_level_dir to an absolute path
        resolved_top_level_dir = requested_top_level_dir.resolve(strict=False)

        # Ensure the resolved path is within the user's files directory
        user_files_dir = Path(f"/files/{requester.email}").resolve(strict=False)
        if not resolved_top_level_dir.is_relative_to(user_files_dir):
            msg = f"The top_level_dir must be in the user's files directory: /files/{requester.email}"  # noqa: E501
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        request.data["owner"] = requester.id
        post_serializer = CapturePostSerializer(
            data=request.data,
        )
        if post_serializer.is_valid():
            post_serializer.save()
        else:
            return Response(post_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # get capture object from serializer
        capture_data = dict(post_serializer.data)
        capture = Capture.objects.get(
            uuid=capture_data["uuid"],
            owner=requester,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            tmp_dir_path, files_to_connect = reconstruct_tree(
                target_dir=Path(temp_dir),
                top_level_dir=requested_top_level_dir,
                owner=requester,
            )

            for cur_file in files_to_connect:
                cur_file.capture = capture
                cur_file.save()

            if not isinstance(channel, str):
                msg = "Channel must be a string."
                return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

            validated_metadata = validate_metadata_by_channel(tmp_dir_path, channel)
            index_capture_metadata(capture, validated_metadata)

        get_serializer = CaptureGetSerializer(capture)

        return Response(get_serializer.data, status=status.HTTP_201_CREATED)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="Capture UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: CaptureGetSerializer,
            404: OpenApiResponse(description="Not Found"),
        },
        examples=[
            OpenApiExample(
                "Example Capture Response",
                summary="Capture Response Body",
                value=example_schema.capture_response_example_schema,
                response_only=True,
            ),
        ],
        description="Retrieve a capture object and its indexed metadata.",
        summary="Retrieve Capture",
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        if pk is None:
            return Response(
                {"detail": "Capture UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=request.user,
        )
        serializer = CaptureGetSerializer(target_capture, many=False)
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="capture_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Type of capture to filter by (e.g. 'drf')",
            ),
        ],
        responses={
            200: CaptureGetSerializer,
            404: OpenApiResponse(description="Not Found"),
            503: OpenApiResponse(description="OpenSearch service unavailable"),
            400: OpenApiResponse(description="Bad Request"),
        },
        description="List captures with optional metadata filtering.",
        summary="List Captures",
    )
    def list(self, request: Request) -> Response:
        """List captures with optional metadata filtering."""
        # Get capture type from query params
        capture_type = request.GET.get("capture_type", None)

        # Start with base queryset filtered by user
        captures = Capture.objects.filter(owner=request.user)

        # Filter by capture type if provided
        if capture_type:
            captures = captures.filter(capture_type=capture_type)

        try:
            # Serialize and return results
            serializer = CaptureGetSerializer(captures, many=True)
            data = serializer.data
            if not data:
                return Response(
                    {"detail": "No captures found"},
                    status=status.HTTP_404_NOT_FOUND,
                )
            return Response(data)
        except ValueError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except os_exceptions.ConnectionError:
            return Response(
                {"detail": "OpenSearch service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (
            os_exceptions.RequestError,
            os_exceptions.OpenSearchException,
        ) as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_400_BAD_REQUEST,
            )
