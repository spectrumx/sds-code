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
from django.http import Http404
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
from sds_gateway.api_methods.helpers.index_handling import retrieve_indexed_metadata
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
from sds_gateway.visualizations.models import PostProcessedData
from sds_gateway.visualizations.models import ProcessingStatus
from sds_gateway.visualizations.processing.utils import reconstruct_drf_files
from sds_gateway.visualizations.processing.waterfall import FFT_SIZE
from sds_gateway.visualizations.processing.waterfall import SAMPLES_PER_SLICE
from sds_gateway.visualizations.processing.waterfall import compute_slices_on_demand
from sds_gateway.visualizations.serializers import PostProcessedDataSerializer

MAX_CAPTURE_NAME_LENGTH = 255  # Maximum length for capture names
MAX_SLICE_BATCH_SIZE = 100  # Maximum number of slices that can be requested at once
UNIX_TIMESTAMP_THRESHOLD = (
    1_000_000_000  # Year 2000 in seconds (for timestamp detection)
)


def _validate_slice_indices(
    start_index_str: str | None, end_index_str: str | None
) -> tuple[int, int] | Response:
    """Validate and parse slice index parameters.

    Args:
        start_index_str: Start index as string from query params
        end_index_str: End index as string from query params

    Returns:
        Tuple of (start_index, end_index) if valid, or Response with error if invalid
    """
    # Validate required parameters
    if start_index_str is None or end_index_str is None:
        return Response(
            {"error": ("Both start_index and end_index query parameters are required")},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate and convert indices to integers
    try:
        start_index = int(start_index_str)
        end_index = int(end_index_str)
    except ValueError:
        return Response(
            {"error": "start_index and end_index must be integers"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate index range
    if start_index < 0:
        return Response(
            {"error": "start_index must be non-negative"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if end_index <= start_index:
        return Response(
            {"error": "end_index must be greater than start_index"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Validate batch size to prevent excessive memory usage
    batch_size = end_index - start_index
    if batch_size > MAX_SLICE_BATCH_SIZE:
        return Response(
            {
                "error": (
                    f"Cannot request more than {MAX_SLICE_BATCH_SIZE} slices "
                    f"at once. Requested: {batch_size}"
                )
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    return (start_index, end_index)


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

    def _get_processed_data_for_capture(
        self,
        request: Request,
        pk: str | None,
        processing_type: str,
    ) -> tuple[Capture, PostProcessedData]:
        """Get the capture and its completed processed data.

        Args:
            request: The DRF request object
            pk: The capture primary key (UUID)
            processing_type: Type of processing (e.g., 'waterfall', 'spectrogram')

        Returns:
            Tuple of (Capture, PostProcessedData)

        Raises:
            Http404: If capture not found, no completed processed data exists,
                     or data file is missing
        """
        capture = get_object_or_404(
            Capture,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        # Get the most recent completed post-processed data
        processed_data = (
            capture.visualization_post_processed_data.filter(
                processing_type=processing_type,
                processing_status=ProcessingStatus.Completed.value,
            )
            .order_by("-created_at")
            .first()
        )

        if not processed_data:
            msg = f"No completed {processing_type} data found for this capture"
            raise Http404(msg)

        if not processed_data.data_file:
            msg = f"Post-processed data file not found for {processing_type}"
            raise Http404(msg)

        return capture, processed_data

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
    def download_post_processed_data(
        self, request: Request, pk: str | None = None
    ) -> Response | FileResponse:
        """Download post-processed data file for a capture."""
        processing_type = request.query_params.get("processing_type")

        if not processing_type:
            return Response(
                {"error": "processing_type parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            _, processed_data = self._get_processed_data_for_capture(
                request, pk, processing_type
            )

            # Return the file as a download response
            response = FileResponse(
                processed_data.data_file, content_type="application/octet-stream"
            )
            response["Content-Disposition"] = (
                f'attachment; filename="{processed_data.data_file.name.split("/")[-1]}"'
            )
            return response  # noqa: TRY300

        except Http404 as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start_index",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Starting slice index (0-based)",
            ),
            OpenApiParameter(
                name="end_index",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Ending slice index (exclusive)",
            ),
            OpenApiParameter(
                name="processing_type",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Type of post-processing (default: 'waterfall')",
            ),
        ],
        responses={
            200: OpenApiResponse(description="Waterfall slices data"),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(
                description="Capture or post-processed data not found"
            ),
        },
        summary="Get waterfall slices by range",
        description=(
            "Get a range of waterfall slices for streaming. "
            "Returns slices from start_index (inclusive) to end_index (exclusive)."
        ),
    )
    @action(detail=True, methods=["get"])
    def waterfall_slices(  # noqa: PLR0911
        self, request: Request, pk: str | None = None
    ) -> Response:
        """Get waterfall slices by index range for streaming."""
        # Get query parameters
        processing_type = request.query_params.get("processing_type", "waterfall")
        start_index_str = request.query_params.get("start_index")
        end_index_str = request.query_params.get("end_index")

        # Validate slice indices using shared helper
        validation_result = _validate_slice_indices(start_index_str, end_index_str)
        if isinstance(validation_result, Response):
            return validation_result
        start_index, end_index = validation_result

        try:
            _, processed_data = self._get_processed_data_for_capture(
                request, pk, processing_type
            )

            # Read and parse the JSON file
            try:
                processed_data.data_file.seek(0)
                waterfall_json = json.load(processed_data.data_file)
            except (OSError, json.JSONDecodeError) as e:
                log.error(f"Failed to read waterfall JSON file for capture {pk}: {e}")
                return Response(
                    {"error": "Failed to read waterfall data file"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # Validate that waterfall_json is a list
            if not isinstance(waterfall_json, list):
                return Response(
                    {"error": "Invalid waterfall data format"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            total_slices = len(waterfall_json)

            # Validate indices against total slices
            if start_index >= total_slices:
                return Response(
                    {
                        "error": (
                            f"start_index ({start_index}) exceeds total slices "
                            f"({total_slices})"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Clamp end_index to total_slices if it exceeds
            end_index = min(end_index, total_slices)

            # Extract the requested slice range
            requested_slices = waterfall_json[start_index:end_index]

            # Get metadata from processed_data
            metadata = processed_data.metadata or {}

            # Build response
            response_data = {
                "slices": requested_slices,
                "total_slices": total_slices,
                "start_index": start_index,
                "end_index": end_index,
                "metadata": metadata,
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except Http404 as e:
            return Response(
                {"error": str(e)},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValueError, OSError, KeyError) as e:
            log.error(f"Unexpected error in waterfall_slices endpoint: {e}")
            return Response(
                {"error": "An unexpected error occurred"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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

    @extend_schema(
        responses={
            200: OpenApiResponse(
                description="Waterfall metadata for streaming visualization"
            ),
            400: OpenApiResponse(description="Bad Request - not a DRF capture"),
            404: OpenApiResponse(description="Capture not found"),
            500: OpenApiResponse(description="Internal Server Error"),
        },
        summary="Get waterfall metadata for streaming (no preprocessing required)",
        description=(
            "Get metadata for waterfall visualization without triggering "
            "preprocessing. Returns total_slices, frequency bounds, and other "
            "metadata immediately. Use this endpoint to initialize the streaming "
            "waterfall visualization."
        ),
    )
    @action(detail=True, methods=["get"], url_path="waterfall_metadata_stream")
    def waterfall_metadata_stream(self, request, pk=None):
        """Get waterfall metadata without preprocessing for streaming visualization.

        This endpoint computes metadata from capture properties stored in OpenSearch,
        avoiding the need to download files from MinIO. This makes it very fast.
        """

        try:
            capture = get_object_or_404(
                Capture,
                pk=pk,
                owner=request.user,
                is_deleted=False,
            )

            # Verify this is a DRF capture
            if capture.capture_type != CaptureType.DigitalRF:
                return Response(
                    {"error": "Streaming waterfall only supports DigitalRF captures"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Get metadata from OpenSearch (fast - no file downloads)
            capture_props_dict = retrieve_indexed_metadata([capture])
            capture_props = capture_props_dict.get(str(capture.uuid), {})

            log.debug(
                f"Streaming metadata - capture_props keys: {list(capture_props.keys())}"
            )

            if not capture_props:
                return Response(
                    {"error": "Capture metadata not found in index"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            samples_per_second = capture_props.get("samples_per_second", 0)
            # Bounds can be stored as timestamps (seconds) or as sample indices
            # If values look like UNIX timestamps (> 1000000000), they're in seconds
            start_bound = capture_props.get("start_bound", 0)
            end_bound = capture_props.get("end_bound", 0)
            center_frequencies = capture_props.get("center_frequencies", [0])
            center_freq = center_frequencies[0] if center_frequencies else 0

            if not samples_per_second or not end_bound:
                return Response(
                    {
                        "error": (
                            "Capture missing required metadata "
                            "(samples_per_second, bounds)"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Calculate duration - bounds may be in seconds (timestamps) or samples
            # If bounds look like UNIX timestamps (> year 2000), convert to duration
            if start_bound > UNIX_TIMESTAMP_THRESHOLD:  # Likely a UNIX timestamp
                duration_seconds = end_bound - start_bound
                total_samples = int(duration_seconds * samples_per_second)
                log.debug(
                    f"Using timestamp mode: duration={duration_seconds}s, "
                    f"total_samples={total_samples}"
                )
            else:
                # Bounds are already in samples
                total_samples = end_bound - start_bound
                log.debug(f"Using sample mode: total_samples={total_samples}")
            # Use constants from waterfall module to ensure consistency
            samples_per_slice = SAMPLES_PER_SLICE
            fft_size = FFT_SIZE
            total_slices = total_samples // samples_per_slice

            sample_rate = float(samples_per_second)
            min_frequency = center_freq - sample_rate / 2
            max_frequency = center_freq + sample_rate / 2

            metadata = {
                "center_frequency": center_freq,
                "sample_rate": sample_rate,
                "min_frequency": min_frequency,
                "max_frequency": max_frequency,
                "total_slices": total_slices,
                "slices_processed": 0,
                "fft_size": fft_size,
                "samples_per_slice": samples_per_slice,
                "channel": capture.channel,
            }

            log.info(
                f"Streaming metadata for capture {pk}: {total_slices} total slices, "
                f"sample_rate={sample_rate}"
            )

            return Response(
                {
                    "capture_uuid": str(capture.uuid),
                    "capture_name": capture.name,
                    "channel": capture.channel,
                    "metadata": metadata,
                    "streaming_enabled": True,
                },
                status=status.HTTP_200_OK,
            )

        except Capture.DoesNotExist:
            return Response(
                {"error": "Capture not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValueError, OSError, KeyError, UnknownIndexError) as e:
            log.error(f"Error getting waterfall metadata for capture {pk}: {e}")
            return Response(
                {"error": f"Failed to get waterfall metadata: {e!s}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="start_index",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Starting slice index (inclusive)",
            ),
            OpenApiParameter(
                name="end_index",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Ending slice index (exclusive)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Waterfall slices computed on-demand",
                examples=[
                    OpenApiExample(
                        name="Success",
                        value={
                            "slices": [{"data": "base64...", "timestamp": "..."}],
                            "total_slices": 12000000,
                            "start_index": 0,
                            "end_index": 100,
                            "metadata": {},
                        },
                    )
                ],
            ),
            400: OpenApiResponse(description="Bad Request"),
            404: OpenApiResponse(description="Capture not found"),
            500: OpenApiResponse(description="Internal Server Error"),
        },
        summary="Get waterfall slices computed on-demand (streaming)",
        description=(
            "Compute and return waterfall slices on-demand without preprocessing. "
            "This endpoint computes FFTs in real-time for the requested slice range. "
            "Maximum batch size is 100 slices per request."
        ),
    )
    @action(detail=True, methods=["get"], url_path="waterfall_slices_stream")
    def waterfall_slices_stream(self, request, pk=None):
        """Compute and return waterfall slices on-demand for streaming visualization."""
        try:
            capture = get_object_or_404(
                Capture,
                pk=pk,
                owner=request.user,
                is_deleted=False,
            )

            # Verify this is a DRF capture
            if capture.capture_type != CaptureType.DigitalRF:
                return Response(
                    {"error": "Streaming waterfall only supports DigitalRF captures"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Validate slice indices using shared helper
            start_index_str = request.query_params.get("start_index")
            end_index_str = request.query_params.get("end_index")
            validation_result = _validate_slice_indices(start_index_str, end_index_str)
            if isinstance(validation_result, Response):
                return validation_result
            start_index, end_index = validation_result

            # Get capture files
            capture_files = capture.files.filter(is_deleted=False)
            if not capture_files.exists():
                return Response(
                    {"error": "No files found for this capture"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # Reconstruct DRF files and compute slices on-demand
            # Note: reconstruct_drf_files uses persistent cache, but temp_path parameter
            # is required for API compatibility. We pass a dummy path since it's unused.
            dummy_temp_path = Path(tempfile.gettempdir()) / "unused"
            drf_path = reconstruct_drf_files(capture, capture_files, dummy_temp_path)
            result = compute_slices_on_demand(
                drf_path, capture.channel, start_index, end_index
            )

            return Response(result, status=status.HTTP_200_OK)

        except Capture.DoesNotExist:
            return Response(
                {"error": "Capture not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except (ValueError, OSError, KeyError) as e:
            log.error(f"Error computing waterfall slices for capture {pk}: {e}")
            return Response(
                {"error": f"Failed to compute waterfall slices: {e!s}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
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
