import tempfile
from pathlib import Path
from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

import sds_gateway.api_methods.utils.swagger_example_schema as example_schema
from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.extract_drf_metadata import (
    validate_metadata_by_channel,
)
from sds_gateway.api_methods.helpers.index_handling import index_capture_metadata
from sds_gateway.api_methods.helpers.reconstruct_file_tree import destroy_tree
from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.capture_serializers import (
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
                description="This is an example of a capture request body.",
                value=example_schema.capture_request_example_schema,
                request_only=True,
            ),
            OpenApiExample(
                "Example Capture Response",
                summary="Capture Response Body",
                description="This is an example of a capture response body.",
                value=example_schema.capture_response_example_schema,
                response_only=True,
            ),
        ],
        description="Create a capture object, connect files to the capture, and index its metadata.",  # noqa: E501
        summary="Create Capture",
    )
    def create(self, request):
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

            validated_metadata = validate_metadata_by_channel(tmp_dir_path, channel)
            index_capture_metadata(capture, validated_metadata)
            destroy_tree(temp_dir)

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
                description="This is an example of a capture response body.",
                value=example_schema.capture_response_example_schema,
                response_only=True,
            ),
        ],
        description="Retrieve a capture object and its indexed metadata.",
        summary="Retrieve Capture",
    )
    def retrieve(self, request, pk=None):
        capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=request.user,
        )
        serializer = CaptureGetSerializer(capture, many=False)
        return Response(serializer.data)
