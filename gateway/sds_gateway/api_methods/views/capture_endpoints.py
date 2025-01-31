import tempfile
from pathlib import Path
from typing import Any
from typing import cast

from django.shortcuts import get_object_or_404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiExample
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from loguru import logger as log
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
from sds_gateway.api_methods.views.file_endpoints import sanitize_path_rel_to_user
from sds_gateway.users.models import User


class CaptureViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def ingest_capture(
        self,
        capture: Capture,
        top_level_dir: Path,
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

            capture_props: dict[str, Any] = {}

            # validate the metadata
            match cap_type := capture.capture_type:
                case CaptureType.DigitalRF:
                    if channel:
                        capture_props = validate_metadata_by_channel(
                            data_path=tmp_dir_path,
                            channel_name=channel,
                        )
                    else:
                        msg = "Channel is required for DigitalRF captures"
                        log.warning(msg)
                        raise ValueError(msg)
                case CaptureType.RadioHound:
                    rh_metadata_file = find_rh_metadata_file(tmp_dir_path)
                    rh_data = load_rh_file(rh_metadata_file)  # may raise ValueError too
                    capture_props = rh_data.model_dump(mode="json")
                case _:
                    msg = f"Unrecognized capture type '{cap_type}'"
                    log.warning(msg)
                    raise ValueError(msg)

            # index the capture properties
            if capture_props:
                index_capture_metadata(capture=capture, capture_props=capture_props)
            else:
                msg = f"No metadata found for capture '{capture.uuid}'"
                log.warning(msg)
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
        """Create a capture object, connecting files and indexing the metadata."""
        channel = request.data.get("channel", None)
        capture_type = request.data.get("capture_type", None)
        log.info(f"Received capture_type: '{capture_type}' {type(capture_type)}")
        log.info(f"Received channel: '{channel}' {type(channel)}")

        unsafe_top_level_dir = request.data.get("top_level_dir", "")

        if channel is not None and not isinstance(channel, str):
            msg = "Channel must be a string."
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        # sanitize top_level_dir
        requested_top_level_dir = sanitize_path_rel_to_user(
            unsafe_path=unsafe_top_level_dir,
            request=request,
        )
        if requested_top_level_dir is None:
            return Response(
                {"detail": "The provided `top_level_dir` is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        requester = cast(User, request.user)
        request_data = request.data.copy()
        post_serializer = CapturePostSerializer(
            data=request_data,
            context={"request_user": request.user},
        )
        if not post_serializer.is_valid():
            errors = post_serializer.errors
            log.error(f"Capture POST serializer errors: {errors}")
            return Response(
                {"detail": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        capture = post_serializer.save()

        try:
            self.ingest_capture(
                capture=capture,
                channel=channel,
                requester=requester,
                top_level_dir=requested_top_level_dir,
            )
        except ValueError as e:
            msg = f"Error handling metadata for capture '{capture.uuid}': {e}"
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        except os_exceptions.ConnectionError as e:
            msg = f"Error connecting to OpenSearch: {e}"
            log.error(msg)
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

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
