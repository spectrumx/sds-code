import logging
import tempfile
from pathlib import Path
from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from opensearchpy import exceptions as os_exceptions
from rest_framework import status
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

import sds_gateway.api_methods.utils.swagger_example_schema as example_schema
from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.extract_drf_metadata import (
    validate_metadata_by_channel,
)
from sds_gateway.api_methods.helpers.index_handling import index_capture_metadata
from sds_gateway.api_methods.helpers.reconstruct_file_tree import find_rh_metadata_file
from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.helpers.rh_schema_generator import load_rh_file
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.capture_serializers import (
    CapturePostSerializer,
)
from sds_gateway.users.models import User

log = logging.getLogger(__name__)


class CaptureViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def handle_metadata(
        self,
        capture: Capture,
        top_level_dir: Path,
        capture_type: CaptureType,
        channel: str | None,
        requester: User,
    ):
        with tempfile.TemporaryDirectory() as temp_dir:
            # Reconstruct the file tree in a temporary directory
            tmp_dir_path, files_to_connect = reconstruct_tree(
                target_dir=Path(temp_dir),
                top_level_dir=top_level_dir,
                owner=requester,
            )

            # Connect the files to the capture
            for cur_file in files_to_connect:
                cur_file.capture = capture
                cur_file.save()

            capture_props = None
            # Validate the metadata and index it
            if capture_type == CaptureType.DigitalRF:
                if channel:
                    capture_props = validate_metadata_by_channel(tmp_dir_path, channel)
                else:
                    msg = "Channel is required for DigitalRF captures"
                    log.exception(msg)
                    raise ValueError(msg)
            elif capture_type == CaptureType.RadioHound:
                rh_metadata_file = find_rh_metadata_file(tmp_dir_path)
                rh_data = load_rh_file(rh_metadata_file)
                capture_props = rh_data.model_dump(mode="json")

            if capture_props:
                index_capture_metadata(capture, capture_props)
            else:
                msg = f"No metadata found for capture '{capture.uuid}'"
                log.exception(msg)
                raise ValueError(msg)

    @extend_schema(
        request=CapturePostSerializer,
        responses={
            201: CaptureGetSerializer,
            400: OpenApiResponse(description="Bad Request"),
            503: OpenApiResponse(description="OpenSearch service unavailable"),
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
        capture_type = request.data.get("capture_type", None)
        log.info(
            "Received capture_type: %s, type: %s",
            capture_type,
            type(capture_type),
        )

        # path to directory that contains the channel dirs
        requested_top_level_dir = Path(request.data.get("top_level_dir", ""))
        requester = cast(User, request.user)

        # Validate path and permissions
        user_files_dir = Path(f"/files/{requester.email}").resolve(strict=False)
        resolved_top_level_dir = requested_top_level_dir.resolve(strict=False)

        if (
            not requested_top_level_dir.is_absolute()
            or not resolved_top_level_dir.is_relative_to(user_files_dir)
        ):
            msg = (
                "The top_level_dir must be an absolute path within: "
                f"/files/{requester.email}"
            )
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # Validate and create capture
        requester = cast(User, request.user)
        request_data = request.data.copy()
        post_serializer = CapturePostSerializer(
            data=request_data,
            context={"request_user": requester},
        )
        if not post_serializer.is_valid():
            return Response(post_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        post_serializer.save()
        capture_data = dict(post_serializer.data)
        capture = Capture.objects.get(uuid=capture_data["uuid"], owner=requester)

        try:
            self.handle_metadata(
                capture,
                requested_top_level_dir,
                CaptureType(capture_type),
                channel,
                requester,
            )
        except ValueError as e:
            msg = f"Error handling metadata for capture '{capture.uuid}': {e}"
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        except os_exceptions.ConnectionError as e:
            msg = f"Error connecting to OpenSearch: {e}"
            return Response({"detail": msg}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(
            CaptureGetSerializer(capture).data,
            status=status.HTTP_201_CREATED,
        )

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
            is_deleted=False,
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

        # Start with base queryset filtered by user and not deleted
        captures = Capture.objects.filter(owner=request.user, is_deleted=False)

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
