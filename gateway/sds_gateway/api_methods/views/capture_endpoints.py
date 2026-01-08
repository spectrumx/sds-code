import json
import re
import tempfile
import uuid
from pathlib import Path
from typing import Any
from typing import cast

from django.db import transaction
from django.db.models import QuerySet
from django.http import FileResponse
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
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

import sds_gateway.api_methods.utils.swagger_example_schema as example_schema
from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.extract_drf_metadata import (
    validate_metadata_by_channel,
)
from sds_gateway.api_methods.helpers.index_handling import UnknownIndexError
from sds_gateway.api_methods.helpers.index_handling import index_capture_metadata
from sds_gateway.api_methods.helpers.reconstruct_file_tree import find_rh_metadata_file
from sds_gateway.api_methods.helpers.reconstruct_file_tree import reconstruct_tree
from sds_gateway.api_methods.helpers.rh_schema_generator import load_rh_file
from sds_gateway.api_methods.helpers.search_captures import get_composite_captures
from sds_gateway.api_methods.helpers.search_captures import search_captures
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import ProcessingType
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.capture_serializers import (
    CapturePostSerializer,
)
from sds_gateway.api_methods.serializers.capture_serializers import (
    serialize_capture_or_composite,
)
from sds_gateway.api_methods.tasks import start_capture_post_processing
from sds_gateway.api_methods.utils.asset_access_control import (
    user_has_access_to_capture,
)
from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.utils.relationship_utils import get_capture_files
from sds_gateway.api_methods.views.file_endpoints import sanitize_path_rel_to_user
from sds_gateway.users.models import User
from sds_gateway.visualizations.serializers import PostProcessedDataSerializer

MAX_CAPTURE_NAME_LENGTH = 255  # Maximum length for capture names


class CapturePagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class CaptureViewSet(viewsets.ViewSet):
    authentication_classes = [SessionAuthentication, APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def _validate_and_index_metadata(
        self,
        capture: Capture,
        data_path: Path,
        drf_channel: str | None = None,
    ) -> None:
        """Validate and index metadata for a capture.

        Args:
            capture:        The capture to validate and index metadata for
            data_path:      Path to directory containing metadata or metadata file
            drf_channel:    Channel name for DigitalRF captures
        Raises:
            ValueError:     If metadata is invalid or not found
        """
        capture_props: dict[str, Any] = {}

        # validate the metadata
        match cap_type := capture.capture_type:
            case CaptureType.DigitalRF:
                if drf_channel:
                    capture_props = validate_metadata_by_channel(
                        data_path=data_path,
                        channel_name=drf_channel,
                    )
                else:
                    msg = "Channel is required for Digital-RF captures"
                    log.warning(msg)
                    raise ValueError(msg)
            case CaptureType.RadioHound:
                rh_metadata_file = find_rh_metadata_file(data_path)
                rh_data = load_rh_file(rh_metadata_file)
                capture_props = rh_data.model_dump(mode="json")
            case _:
                msg = f"Unrecognized capture type '{cap_type}'"
                log.warning(msg)
                raise ValueError(msg)

        # index the capture properties
        if capture_props:
            index_capture_metadata(
                capture=capture,
                capture_props=capture_props,
            )
        else:
            msg = f"No metadata found for capture '{capture.uuid}'"
            log.warning(msg)
            raise ValueError(msg)

    def ingest_capture(
        self,
        capture: Capture,
        *,
        drf_channel: str | None,
        requester: User,
        rh_scan_group: uuid.UUID | None,
        top_level_dir: Path,
    ) -> None:
        """Ingest or update a capture by handling files and metadata.

        This function can be used for both creating new captures
        and updating existing ones.

        Args:
            capture:        The capture to ingest or update
            drf_channel:    Channel name for DigitalRF captures
            requester:      The user making the request
            rh_scan_group:  Optional scan group UUID for RH captures
            top_level_dir:  Path to directory containing files to connect to capture
        """
        # check if the top level directory was passed
        if not top_level_dir:
            msg = "No top level directory provided for capture ingestion"
            log.warning(msg)
            raise ValueError(msg)

        # normalize top level directory under user
        user_file_prefix = f"/files/{requester.email!s}"
        if not str(top_level_dir).startswith(user_file_prefix):
            top_level_dir = Path(f"{user_file_prefix!s}{top_level_dir!s}")

        with tempfile.TemporaryDirectory() as temp_dir:
            # reconstruct the file tree in a temporary directory
            tmp_dir_path, files_to_connect = reconstruct_tree(
                target_dir=Path(temp_dir),
                virtual_top_dir=top_level_dir,
                owner=requester,
                capture_type=capture.capture_type,
                drf_channel=drf_channel,
                rh_scan_group=rh_scan_group,
                verbose=False,
            )

            # try to validate and index metadata before connecting files
            self._validate_and_index_metadata(
                capture=capture,
                data_path=tmp_dir_path,
                drf_channel=drf_channel,
            )

            # disconnect files that are no longer in the capture
            all_current_files = get_capture_files(
                capture, include_deleted=True
            )  # Include deleted for cleanup
            for cur_file in all_current_files:
                if cur_file not in files_to_connect:
                    cur_file.captures.remove(capture)
                    # Also clear FK if it exists
                    # (for backward compatibility during migration)
                    if cur_file.capture == capture:
                        cur_file.capture = None
                        cur_file.save(update_fields=["capture"])

            # connect the files to the capture
            for cur_file in files_to_connect:
                cur_file.captures.add(capture)

            if not files_to_connect:
                msg = (
                    f"No files found for capture '{capture.uuid}' at '{top_level_dir}'"
                )
                log.warning(msg)
                raise ValueError(msg)

            log.info(
                f"Connected {len(files_to_connect)} files to capture '{capture.uuid}'",
            )

    def _trigger_post_processing(self, capture: Capture) -> None:
        """Trigger post-processing for a DigitalRF capture after OpenSearch indexing.

        Args:
            capture: The capture to trigger post-processing for
        """
        if capture.capture_type != CaptureType.DigitalRF:
            return

        log.info(
            f"Triggering visualization processing for DigitalRF capture: {capture.uuid}"
        )

        try:
            # Use the Celery task for post-processing to ensure proper async execution
            # Launch the visualization processing task asynchronously
            processing_config = {
                ProcessingType.Waterfall.value: {},
                ProcessingType.Spectrogram.value: {},
            }

            result = start_capture_post_processing.delay(
                str(capture.uuid), processing_config
            )
            log.info(
                f"Launched visualization processing task for capture {capture.uuid}, "
                f"task_id: {result.id}"
            )

        except Exception as e:  # noqa: BLE001
            log.error(
                f"Failed to launch visualization processing task for capture "
                f"{capture.uuid}: {e}"
            )

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
                value=example_schema.example_cap_creation_request,
                request_only=True,
            ),
            OpenApiExample(
                "Example Capture Response",
                summary="Capture Response Body",
                value=example_schema.example_cap_creation_response,
                response_only=True,
            ),
        ],
        description=(
            "Create a capture object, connect files to the capture, "
            "and index its metadata."
        ),
        summary="Create Capture",
    )
    def _validate_create_request(
        self, request: Request
    ) -> tuple[Response | None, dict[str, Any] | None]:
        """Validate the create request and return response or validated data."""
        drf_channel = request.data.get("channel", None)
        rh_scan_group = request.data.get("scan_group", None)
        capture_type = request.data.get("capture_type", None)
        log.debug(
            f"Creating capture: type={capture_type}, channel={drf_channel}, "
            f"scan_group={rh_scan_group}"
        )

        if capture_type is None:
            return Response(
                {"detail": "The `capture_type` field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            ), None

        unsafe_top_level_dir = request.data.get("top_level_dir", "")
        requested_top_level_dir = sanitize_path_rel_to_user(
            unsafe_path=unsafe_top_level_dir,
            request=request,
        )
        if requested_top_level_dir is None:
            return Response(
                {"detail": "The provided `top_level_dir` is invalid."},
                status=status.HTTP_400_BAD_REQUEST,
            ), None

        if capture_type == CaptureType.DigitalRF.value and not drf_channel:
            return Response(
                {"detail": "The `channel` field is required for DigitalRF captures."},
                status=status.HTTP_400_BAD_REQUEST,
            ), None

        requester = cast("User", request.user)
        request_data = request.data.copy()
        # Convert string to CaptureType enum
        capture_type_enum = CaptureType(capture_type)
        request_data["index_name"] = infer_index_name(capture_type_enum)

        post_serializer = CapturePostSerializer(
            data=request_data,
            context={"request_user": request.user},
        )
        if not post_serializer.is_valid():
            errors = post_serializer.errors
            log.warning(f"Capture POST serializer errors: {errors}")
            return Response(
                {"detail": errors},
                status=status.HTTP_400_BAD_REQUEST,
            ), None

        capture_candidate: dict[str, Any] = post_serializer.validated_data

        try:
            _check_capture_creation_constraints(capture_candidate, owner=requester)
            log.info("Constraint check passed, proceeding with capture creation")
        except ValueError as err:
            msg = "One or more capture creation constraints violated:"
            for error in err.args[0].splitlines():
                msg += f"\n\t{error}"
            log.warning(f"Constraint check failed: {msg}")
            return Response(
                {"detail": msg},
                status=status.HTTP_400_BAD_REQUEST,
            ), None

        return None, {
            "drf_channel": drf_channel,
            "rh_scan_group": rh_scan_group,
            "requested_top_level_dir": requested_top_level_dir,
            "requester": requester,
            "capture_candidate": capture_candidate,
        }

    def _handle_capture_creation_errors(
        self, capture: Capture, error: Exception
    ) -> Response:
        """Handle errors during capture creation and cleanup."""
        if isinstance(error, UnknownIndexError):
            user_msg = f"Unknown index: '{error}'. Try recreating this capture."
            server_msg = (
                f"Unknown index: '{error}'. Try running the init_indices "
                "subcommand if this is index should exist."
            )
            log.error(server_msg)
            # Transaction will automatically rollback, so no need to manually delete
            return Response({"detail": user_msg}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(error, ValueError):
            user_msg = f"Error handling metadata for capture '{capture.uuid}': {error}"
            # Transaction will automatically rollback, so no need to manually delete
            return Response({"detail": user_msg}, status=status.HTTP_400_BAD_REQUEST)
        if isinstance(error, os_exceptions.ConnectionError):
            user_msg = f"Error connecting to OpenSearch: {error}"
            log.error(user_msg)
            # Transaction will automatically rollback, so no need to manually delete
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        # Re-raise unexpected errors
        raise error

    def create(self, request: Request) -> Response:
        """Create a capture object, connecting files and indexing the metadata."""
        # Validate request
        response, validated_data = self._validate_create_request(request)
        if response is not None:
            return response

        if validated_data is None:
            return Response(
                {"detail": "Validation failed but no specific error was returned."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        drf_channel = validated_data["drf_channel"]
        rh_scan_group = validated_data["rh_scan_group"]
        requested_top_level_dir = validated_data["requested_top_level_dir"]
        requester = validated_data["requester"]

        # Create the capture within a transaction
        capture = None
        try:
            with transaction.atomic():
                post_serializer = CapturePostSerializer(
                    data=request.data.copy(),
                    context={"request_user": request.user},
                )
                post_serializer.is_valid()
                capture = cast("Capture", post_serializer.save())

                self.ingest_capture(
                    capture=capture,
                    drf_channel=drf_channel,
                    rh_scan_group=rh_scan_group,
                    requester=requester,
                    top_level_dir=requested_top_level_dir,
                )

            # If we get here, the transaction was successful
            get_serializer = CaptureGetSerializer(capture)
            return Response(get_serializer.data, status=status.HTTP_201_CREATED)

        except (UnknownIndexError, ValueError, os_exceptions.ConnectionError) as e:
            # Transaction will auto-rollback, no manual deletion needed
            if isinstance(capture, Capture):
                return self._handle_capture_creation_errors(capture=capture, error=e)
            return Response(
                {"detail": "An unexpected error occurred."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
                value=example_schema.example_cap_creation_response,
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
            is_deleted=False,
        )

        # Check if the user has access to the capture
        if not user_has_access_to_capture(request.user, target_capture):
            return Response(
                {"detail": "You do not have permission to access this capture."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Use composite capture serialization
        capture_data = serialize_capture_or_composite(
            target_capture, context={"request": request}
        )
        return Response(capture_data)

    def _validate_metadata_filters(
        self,
        metadata_filters_str: str | None,
    ) -> list[dict[str, Any]] | None:
        """Parse and validate metadata filters from request."""
        if not metadata_filters_str:
            return None

        try:
            metadata_filters = json.loads(metadata_filters_str)
            if not isinstance(metadata_filters, list):
                msg = "'metadata_filters' must be a list."
                log.warning(msg)
                raise TypeError(msg)
            return metadata_filters  # noqa: TRY300
        except json.JSONDecodeError as err:
            msg = "'metadata_filters' could not be parsed from request"
            log.warning(msg)
            raise ValueError(msg) from err

    def _paginate_captures(
        self,
        captures: QuerySet[Capture],
        request: Request,
    ) -> Response:
        """Paginate and serialize capture results."""
        paginator = CapturePagination()
        paginated_captures = paginator.paginate_queryset(captures, request=request)
        serializer = CaptureGetSerializer(paginated_captures, many=True)
        return paginator.get_paginated_response(serializer.data)

    def _paginate_composite_captures(
        self,
        captures: QuerySet[Capture],
        request: Request,
    ) -> Response:
        """Paginate and serialize composite capture results."""

        # Get composite captures
        composite_captures = get_composite_captures(captures)

        # Manual pagination for composite captures
        paginator = CapturePagination()
        page_size = cast("int", paginator.get_page_size(request))
        page_number = cast(
            "int",
            paginator.get_page_number(request, paginator=paginator),  # pyright: ignore[reportArgumentType]
        )

        start_index = (page_number - 1) * page_size
        end_index = start_index + page_size

        paginated_composites = composite_captures[start_index:end_index]

        # Create custom paginated response
        total_count = len(composite_captures)
        next_url = None
        previous_url = None

        if end_index < total_count:
            next_url = request.build_absolute_uri(
                f"{request.path}?page={page_number + 1}&page_size={page_size}"
            )

        if page_number > 1:
            previous_url = request.build_absolute_uri(
                f"{request.path}?page={page_number - 1}&page_size={page_size}"
            )

        return Response(
            {
                "count": total_count,
                "next": next_url,
                "previous": previous_url,
                "results": paginated_composites,
            }
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="capture_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Type of capture to filter by (e.g. 'drf')",
            ),
            OpenApiParameter(
                name="metadata_filters",
                type=OpenApiTypes.OBJECT,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Metadata filters to apply to the search",
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
                default=CapturePagination.page_size,
            ),
        ],
        responses={
            200: CaptureGetSerializer,
            404: OpenApiResponse(description="Not Found"),
            503: OpenApiResponse(description="OpenSearch service unavailable"),
            400: OpenApiResponse(description="Bad Request"),
        },
        examples=[
            OpenApiExample(
                "Example Capture List Request",
                summary="Capture List Request Body",
                value=example_schema.capture_list_request_example_schema,
                request_only=True,
            ),
            OpenApiExample(
                "Example Capture List Response",
                summary="Capture List Response Body",
                value=example_schema.capture_list_response_example_schema,
                response_only=True,
            ),
        ],
        description="List captures with optional metadata filtering.",
        summary="List Captures",
    )
    def list(self, request: Request) -> Response:
        """List captures with optional metadata filtering."""
        capture_type_raw = request.GET.get("capture_type", None)

        try:
            capture_type = CaptureType(capture_type_raw) if capture_type_raw else None
            metadata_filters = self._validate_metadata_filters(
                request.GET.get("metadata_filters"),
            )
            captures = search_captures(
                capture_type=capture_type,
                metadata_filters=metadata_filters,
                owner=cast("User", request.user),
            )
            return self._paginate_composite_captures(captures=captures, request=request)
        except (ValueError, TypeError) as err:
            return Response(
                {"detail": str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except os_exceptions.ConnectionError as err:
            try:
                log.exception(err)
            except Exception:  # noqa: BLE001
                # used in tests when mocking this exception
                log.error("OpenSearch connection error")
            return Response(
                {"detail": "Internal service unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except (
            os_exceptions.RequestError,
            os_exceptions.OpenSearchException,
        ) as err:
            try:
                log.exception(err)
            except Exception:  # noqa: BLE001
                # used in tests when mocking this exception
                log.error(str(err))
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
        request=CapturePostSerializer,
        responses={
            200: CaptureGetSerializer,
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
            503: OpenApiResponse(description="OpenSearch service unavailable"),
        },
        description=(
            "Update a capture by adding files and re-indexing metadata. "
            "Uses the top_level_dir attribute to connect files to the capture and "
            "re-index metadata file to capture changes to the capture properties."
        ),
        summary="Update Capture",
    )
    def update(self, request: Request, pk: str | None = None) -> Response:
        """Update a capture by adding files or re-indexing metadata."""
        if pk is None:
            return Response(
                {"detail": "Capture UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        owner = cast("User", request.user)
        target_capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=owner,  # Require ownership for updates
            is_deleted=False,
        )

        requested_top_level_dir = sanitize_path_rel_to_user(
            unsafe_path=target_capture.top_level_dir,
            user=owner,
        )
        if requested_top_level_dir is None:
            return Response(
                {"detail": "Invalid capture"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            self.ingest_capture(
                capture=target_capture,
                drf_channel=target_capture.channel,
                rh_scan_group=target_capture.scan_group,
                requester=owner,
                top_level_dir=requested_top_level_dir,
            )

            # Trigger post-processing for DigitalRF captures after OpenSearch indexing
            # is complete
            if target_capture.capture_type == CaptureType.DigitalRF:
                # Use transaction.on_commit to ensure the task is queued after the
                # transaction is committed
                transaction.on_commit(
                    lambda: self._trigger_post_processing(target_capture)
                )

        except UnknownIndexError as e:
            user_msg = f"Unknown index: '{e}'. Try recreating this capture."
            server_msg = (
                f"Unknown index: '{e}'. Try running the init_indices "
                "subcommand if this is index should exist."
            )
            log.error(server_msg)
            return Response({"detail": user_msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            msg = f"Error handling metadata for capture '{target_capture.uuid}': {e}"
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)
        except os_exceptions.ConnectionError as e:
            msg = f"Error connecting to OpenSearch: {e}"
            log.error(msg)
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)

        # Return updated capture
        serializer = CaptureGetSerializer(target_capture)
        return Response(serializer.data)

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
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "New name for the capture",
                        "maxLength": 255,
                    }
                },
                "required": ["name"],
            }
        },
        responses={
            200: CaptureGetSerializer,
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Not Found"),
        },
        description="Update the name of a capture.",
        summary="Update Capture Name",
    )
    def partial_update(self, request: Request, pk: str | None = None) -> Response:
        """Update the name of a capture."""
        if pk is None:
            return Response(
                {"detail": "Capture UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=request.user,  # Require ownership for updates
            is_deleted=False,
        )

        # Get the new name from request data
        new_name = request.data.get("name")
        if not new_name:
            return Response(
                {"detail": "Name field is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(new_name) > MAX_CAPTURE_NAME_LENGTH:
            return Response(
                {
                    "detail": (
                        f"Name must be {MAX_CAPTURE_NAME_LENGTH} characters or less."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Update the name
        target_capture.name = new_name.strip()
        target_capture.save(update_fields=["name"])

        # Return updated capture
        serializer = CaptureGetSerializer(target_capture)
        return Response(serializer.data)

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
            204: OpenApiResponse(description="No Content"),
            404: OpenApiResponse(description="Not Found"),
        },
        description="Delete a capture on the server.",
        summary="Delete Capture",
    )
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Delete a capture on the server."""
        if pk is None:
            return Response(
                {"detail": "Capture UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=request.user,  # Require ownership for deletions
            is_deleted=False,
        )

        target_capture.soft_delete()

        # set these properties on OpenSearch document
        opensearch_client = get_opensearch_client()
        try:
            opensearch_client.update(
                index=target_capture.index_name,
                id=target_capture.uuid,
                body={
                    "doc": {
                        "is_deleted": target_capture.is_deleted,
                        "deleted_at": target_capture.deleted_at,
                    },
                },
            )
        except os_exceptions.NotFoundError:
            log.info(
                f"OpenSearch document for capture '{target_capture.uuid}' "
                "not found during soft delete: ignoring missing document.",
            )

        # return status for soft deletion
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    @extend_schema(
        summary="Get post-processing status",
        description="Get the status of post-processing for a capture",
        responses={
            200: OpenApiResponse(
                description="Post-processing status",
                examples=[
                    OpenApiExample(
                        "Success",
                        value={
                            "capture_uuid": "123e4567-e89b-12d3-a456-426614174000",
                            "post_processed_data": [
                                {
                                    "id": 1,
                                    "processing_type": "waterfall",
                                    "processing_status": "completed",
                                    "processed_at": "2024-01-01T12:00:00Z",
                                    "is_ready": True,
                                }
                            ],
                        },
                    )
                ],
            ),
            404: OpenApiResponse(description="Capture not found"),
        },
    )
    def post_processing_status(self, request, pk=None):
        """Get post-processing status for a capture."""
        try:
            capture = get_object_or_404(
                Capture,
                pk=pk,
                owner=request.user,
                is_deleted=False,
            )

            # Get all post-processed data for this capture
            processed_data = capture.visualization_post_processed_data.all().order_by(
                "processing_type", "-created_at"
            )

            return Response(
                {
                    "capture_uuid": str(capture.uuid),
                    "post_processed_data": PostProcessedDataSerializer(
                        processed_data, many=True
                    ).data,
                },
                status=status.HTTP_200_OK,
            )

        except Capture.DoesNotExist:
            return Response(
                {"error": "Capture not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @action(detail=True, methods=["get"])
    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="processing_type",
                description=(
                    "Type of post-processed data to download (e.g., 'waterfall')"
                ),
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={
            200: OpenApiResponse(description="Post-processed data file"),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(
                description="Capture or post-processed data not found"
            ),
        },
        summary="Download post-processed data",
        description="Download a post-processed data file for a capture",
    )
    def download_post_processed_data(self, request, pk=None):
        """Download post-processed data file for a capture."""
        try:
            capture = get_object_or_404(
                Capture,
                pk=pk,
                owner=request.user,
                is_deleted=False,
            )

            processing_type = request.query_params.get("processing_type")

            if not processing_type:
                return Response(
                    {"error": "processing_type parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the most recent post-processed data for this capture and
            # processing type
            processed_data = (
                capture.visualization_post_processed_data.filter(
                    processing_type=processing_type,
                    processing_status="completed",
                )
                .order_by("-created_at")
                .first()
            )

            if not processed_data:
                return Response(
                    {
                        "error": (
                            f"No completed {processing_type} data found for this "
                            "capture"
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            if not processed_data.data_file:
                return Response(
                    {
                        "error": (
                            f"Post-processed data file not found for {processing_type}"
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Return the file as a download response
            response = FileResponse(
                processed_data.data_file, content_type="application/octet-stream"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{processed_data.data_file.name.split("/")[-1]}"'
            )
            return response  # noqa: TRY300

        except Capture.DoesNotExist:
            return Response(
                {"error": "Capture not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="processing_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Type of post-processing (e.g., 'waterfall')",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Post-processed data metadata"),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(
                description="Capture or post-processed data not found"
            ),
        },
        summary="Get post-processed data metadata",
        description="Get metadata for post-processed data",
    )
    @action(detail=True, methods=["get"])
    def get_post_processed_metadata(self, request, pk=None):
        """Get metadata for post-processed data."""
        try:
            capture = get_object_or_404(
                Capture,
                pk=pk,
                owner=request.user,
                is_deleted=False,
            )

            processing_type = request.query_params.get("processing_type")

            if not processing_type:
                return Response(
                    {"error": "processing_type parameter is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get the most recent post-processed data for this capture and
            # processing type
            processed_data = (
                capture.visualization_post_processed_data.filter(
                    processing_type=processing_type,
                    processing_status="completed",
                )
                .order_by("-created_at")
                .first()
            )

            if not processed_data:
                return Response(
                    {
                        "error": (
                            f"No completed {processing_type} data found for this "
                            f"capture"
                        )
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            # Return the metadata
            return Response(
                {
                    "metadata": processed_data.metadata,
                    "processing_type": processed_data.processing_type,
                    "created_at": processed_data.created_at,
                    "processing_parameters": processed_data.processing_parameters,
                }
            )

        except Capture.DoesNotExist:
            return Response(
                {"error": "Capture not found"},
                status=status.HTTP_404_NOT_FOUND,
            )


def _normalize_top_level_dir(top_level_dir: str) -> str:
    """Normalize the top_level_dir to match the database format.

    Args:
        top_level_dir: The path to normalize

    Returns:
        The normalized path with leading slash, whitespace stripped, and multiple
        slashes resolved
    """
    # Strip whitespace from the input
    normalized = top_level_dir.strip()

    # Check for empty string after stripping
    if not normalized:
        msg = "top_level_dir cannot be empty"
        raise ValueError(msg)

    # Ensure leading slash
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    # Resolve multiple consecutive slashes by replacing them with single slashes
    # but preserve the leading slash
    normalized = re.sub(r"/+", "/", normalized)

    # Resolve multiple slashes using Path.resolve()
    try:
        resolved = Path(normalized).resolve(strict=False)
        return str(resolved)
    except (OSError, ValueError):
        # Fallback to original behavior if Path.resolve() fails
        return normalized


def _check_capture_creation_constraints(
    capture_candidate: dict[str, Any],
    owner: User,
) -> None:
    """Check constraints for capture creation. Raise ValueError if any are violated.

    The serializer validation (`is_valid()`) doesn't have the context of which operation
        is being performed (create or update), so we're checking these constraints
        below for capture creations.

    Args:
        capture_candidate:  The capture dict after serializer's validation
                            (`serializer.validated_data`) to check constraints against.
    Raises:
        ValueError:         If any of the constraints are violated.
        AssertionError:     If an internal assertion fails.
    """

    log.debug(
        "No channel and top_level_dir conflictsfor current user's DigitalRF captures."
    )

    capture_type = capture_candidate.get("capture_type")
    top_level_dir = capture_candidate.get("top_level_dir")
    _errors: dict[str, str] = {}

    required_fields = {
        "capture_type": capture_type,
        "top_level_dir": top_level_dir,
    }

    _errors.update(
        {
            field: f"'{field}' is required."
            for field, value in required_fields.items()
            if value is None
        },
    )

    if _errors:
        msg = "Capture creation constraints violated:" + "".join(
            f"\n\t{rule}: {error}" for rule, error in _errors.items()
        )
        log.warning(msg)
        raise AssertionError(msg)

    # capture creation constraints

    # CONSTRAINT: DigitalRF captures must have unique channel and top_level_dir
    if capture_type == CaptureType.DigitalRF:
        channel = capture_candidate.get("channel")

        # Normalize the top_level_dir to match the database format
        normalized_top_level_dir = _normalize_top_level_dir(top_level_dir)

        cap_qs: QuerySet[Capture] = Capture.objects.filter(
            channel=channel,
            top_level_dir=normalized_top_level_dir,
            capture_type=CaptureType.DigitalRF,
            is_deleted=False,
            owner=owner,
        )

        if not channel:
            log.error(
                "No channel provided for DigitalRF capture. This missing "
                "value should have been caught by the serializer validator.",
            )
        elif cap_qs.exists():
            conflicting_capture = cap_qs.first()
            assert conflicting_capture is not None, "QuerySet should not be empty here."
            log.warning(
                f"CONSTRAINT VIOLATION: Found conflicting capture "
                f"{conflicting_capture.uuid} for channel '{channel}' "
                f"and top_level_dir '{top_level_dir}'"
            )
            _errors.update(
                {
                    "drf_unique_channel_and_tld": (
                        "This channel and top level directory are already in use by "
                        f"another capture: {conflicting_capture.pk}"
                    ),
                },
            )
        else:
            log.info(
                f"DigitalRF constraints passed: channel={channel}, "
                f"path={normalized_top_level_dir}"
            )

    # CONSTRAINT: RadioHound captures must have unique scan group
    if capture_type == CaptureType.RadioHound:
        scan_group: str | None = capture_candidate.get("scan_group")
        cap_qs: QuerySet[Capture] = Capture.objects.filter(
            scan_group=scan_group,
            capture_type=CaptureType.RadioHound,
            is_deleted=False,
            owner=owner,
        )
        if scan_group is None:
            # No scan group provided for RadioHound capture
            pass
        elif cap_qs.exists():
            conflicting_capture = cap_qs.first()
            assert conflicting_capture is not None, "QuerySet should not be empty here."
            _errors.update(
                {
                    "rh_unique_scan_group": (
                        f"This scan group is already in use by "
                        f"another capture: {conflicting_capture.pk}"
                    ),
                },
            )
        else:
            log.debug(
                "No `scan_group` conflicts for current user's captures.",
            )

    if _errors:
        msg = "Capture creation constraints violated:"
        for rule, error in _errors.items():
            msg += f"\n\t{rule}: {error}"
        raise ValueError(msg)
