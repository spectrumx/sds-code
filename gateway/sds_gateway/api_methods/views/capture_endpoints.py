import json
import tempfile
import uuid
from pathlib import Path
from typing import Any
from typing import cast

from django.db.models import QuerySet
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
from sds_gateway.api_methods.helpers.search_captures import search_captures
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.serializers.capture_serializers import CaptureGetSerializer
from sds_gateway.api_methods.serializers.capture_serializers import (
    CapturePostSerializer,
)
from sds_gateway.api_methods.utils.metadata_schemas import infer_index_name
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.views.file_endpoints import sanitize_path_rel_to_user
from sds_gateway.users.models import User


class CapturePagination(PageNumberPagination):
    page_size = 30
    page_size_query_param = "page_size"
    max_page_size = 100


class CaptureViewSet(viewsets.ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def _validate_and_index_metadata(
        self,
        capture: Capture,
        data_path: Path,
        drf_channels: list[str] | None = None,
    ) -> None:
        """Validate and index metadata for a capture.

        Args:
            capture:        The capture to validate and index metadata for
            data_path:      Path to directory containing metadata or metadata file
            drf_channels:   List of channel names for DigitalRF captures
        Raises:
            ValueError:     If metadata is invalid or not found
        """
        capture_props: dict[str, Any] = {}
        channel_metadata: dict[str, dict[str, Any]] | None = None

        # validate the metadata
        match cap_type := capture.capture_type:
            case CaptureType.DigitalRF:
                if drf_channels:
                    # For multi-channel DRF captures, validate each channel separately
                    channel_metadata = {}
                    for channel_name in drf_channels:
                        channel_props = validate_metadata_by_channel(
                            data_path=data_path,
                            channel_name=channel_name,
                        )
                        channel_metadata[channel_name] = channel_props

                    # Use the first channel's metadata as the base capture_props for
                    # backward compatibility
                    capture_props = None
                else:
                    msg = "Channels are required for Digital-RF captures"
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
        if capture_props or channel_metadata:
            index_capture_metadata(
                capture=capture,
                capture_props=capture_props,
                channel_metadata=channel_metadata,
            )
        else:
            msg = f"No metadata found for capture '{capture.uuid}'"
            log.warning(msg)
            raise ValueError(msg)

    def ingest_capture(
        self,
        capture: Capture,
        *,
        drf_channels: list[str] | None,
        requester: User,
        rh_scan_group: uuid.UUID | None,
        top_level_dir: Path,
    ) -> None:
        """Ingest or update a capture by handling files and metadata.

        This function can be used for both creating new captures
        and updating existing ones.

        Args:
            capture:        The capture to ingest or update
            drf_channels:   List of channel names for DigitalRF captures
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
            # For backward compatibility, use the first channel if multiple
            # channels provided
            drf_channel = drf_channels[0] if drf_channels else None
            tmp_dir_path, files_to_connect = reconstruct_tree(
                target_dir=Path(temp_dir),
                virtual_top_dir=top_level_dir,
                owner=requester,
                capture_type=capture.capture_type,
                drf_channel=drf_channel,
                rh_scan_group=rh_scan_group,
                verbose=True,
            )

            # try to validate and index metadata before connecting files
            self._validate_and_index_metadata(
                capture=capture,
                data_path=tmp_dir_path,
                drf_channels=drf_channels,
            )

            # disconnect files that are no longer in the capture
            for cur_file in capture.files.all():
                if cur_file not in files_to_connect:
                    cur_file.capture = None
                    cur_file.save()

            # connect the files to the capture
            for cur_file in files_to_connect:
                cur_file.capture = capture
                cur_file.save()

            if not files_to_connect:
                msg = (
                    f"No files found for capture '{capture.uuid}' at '{top_level_dir}'"
                )
                log.warning(msg)
            else:
                log.info(
                    f"Connected {len(files_to_connect)} "
                    f"files to capture '{capture.uuid}'",
                )

    def _validate_capture_request_data(self, request):
        drf_channels = request.data.get("channels", None)
        rh_scan_group = request.data.get("scan_group", None)
        capture_type = request.data.get("capture_type", None)
        if "channel" in request.data:
            deprecated_channel_msg = (
                "The 'channel' parameter is deprecated. Use 'channels' instead. "
                "For single channels, pass as a list: ['channel_name']."
            )
            return (
                None,
                None,
                None,
                Response(
                    {"detail": deprecated_channel_msg},
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
        if capture_type is None:
            return (
                None,
                None,
                None,
                Response(
                    {"detail": "The `capture_type` field is required."},
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
        unsafe_top_level_dir = request.data.get("top_level_dir", "")
        requested_top_level_dir = sanitize_path_rel_to_user(
            unsafe_path=unsafe_top_level_dir,
            request=request,
        )
        if requested_top_level_dir is None:
            return (
                None,
                None,
                None,
                Response(
                    {"detail": "The provided `top_level_dir` is invalid."},
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
        if capture_type == CaptureType.DigitalRF and not drf_channels:
            return (
                None,
                None,
                None,
                Response(
                    {
                        "detail": (
                            "The `channels` field is required for DigitalRF captures."
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                ),
            )
        return drf_channels, rh_scan_group, capture_type, requested_top_level_dir

    def _get_validated_serializer(self, request_data, request_user):
        post_serializer = CapturePostSerializer(
            data=request_data,
            context={"request_user": request_user},
        )
        if not post_serializer.is_valid():
            errors = post_serializer.errors
            log.warning(f"Capture POST serializer errors: {errors}")
            return None, Response(
                {"detail": errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return post_serializer, None

    def _handle_capture_constraints(self, capture_candidate, requester, request_data):
        try:
            _check_capture_creation_constraints(
                capture_candidate, owner=requester, request_data=request_data
            )
        except ValueError as err:
            msg = "One or more capture creation constraints violated:"
            for error in err.args[0].splitlines():
                msg += f"\n\t{error}"
            log.info(msg)
            return Response(
                {"detail": msg},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return None

    def _ingest_and_handle_errors(
        self,
        capture,
        drf_channels,
        rh_scan_group,
        requester,
        requested_top_level_dir,
    ):
        try:
            self.ingest_capture(
                capture=capture,
                drf_channels=drf_channels,
                rh_scan_group=rh_scan_group,
                requester=requester,
                top_level_dir=requested_top_level_dir,
            )
        except UnknownIndexError as e:
            user_msg = f"Unknown index: '{e}'. Try recreating this capture."
            server_msg = (
                f"Unknown index: '{e}'. Try running the init_indices "
                "subcommand if this is index should exist."
            )
            log.error(server_msg)
            capture.soft_delete()
            return Response({"detail": user_msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            user_msg = f"Error handling metadata for capture '{capture.uuid}': {e}"
            capture.soft_delete()
            return Response({"detail": user_msg}, status=status.HTTP_400_BAD_REQUEST)
        except os_exceptions.ConnectionError as e:
            user_msg = f"Error connecting to OpenSearch: {e}"
            log.error(user_msg)
            capture.soft_delete()
            return Response(status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return None

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
    def create(self, request: Request) -> Response:
        """Create a capture object, connecting files and indexing the metadata."""
        (
            drf_channels,
            rh_scan_group,
            capture_type,
            requested_top_level_dir_or_resp,
        ) = self._validate_capture_request_data(request)
        if isinstance(requested_top_level_dir_or_resp, Response):
            return requested_top_level_dir_or_resp
        requested_top_level_dir = requested_top_level_dir_or_resp
        requester = cast("User", request.user)
        request_data = request.data.copy()
        request_data["index_name"] = infer_index_name(capture_type)
        post_serializer, resp = self._get_validated_serializer(
            request_data, request.user
        )
        if resp:
            return resp
        capture_candidate: dict[str, Any] = post_serializer.validated_data
        resp = self._handle_capture_constraints(
            capture_candidate, requester, request.data
        )
        if resp:
            return resp
        capture = post_serializer.save()
        resp = self._ingest_and_handle_errors(
            capture, drf_channels, rh_scan_group, requester, requested_top_level_dir
        )
        if resp:
            return resp
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
            owner=request.user,
            is_deleted=False,
        )
        serializer = CaptureGetSerializer(target_capture, many=False)
        return Response(serializer.data)

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
            return self._paginate_captures(captures=captures, request=request)
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
            owner=owner,
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
                drf_channels=target_capture.channels,
                rh_scan_group=target_capture.scan_group,
                requester=owner,
                top_level_dir=requested_top_level_dir,
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
            owner=request.user,
            is_deleted=False,
        )
        target_capture.soft_delete()

        # set these properties on OpenSearch document
        opensearch_client = get_opensearch_client()
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

        # return status for soft deletion
        return Response(status=status.HTTP_204_NO_CONTENT)


def _check_required_fields(capture_candidate: dict[str, Any]) -> dict[str, str]:
    capture_type = capture_candidate.get("capture_type")
    top_level_dir = capture_candidate.get("top_level_dir")
    required_fields = {
        "capture_type": capture_type,
        "top_level_dir": top_level_dir,
    }
    return {
        field: f"'{field}' is required."
        for field, value in required_fields.items()
        if value is None
    }


def _check_drf_constraints(
    capture_candidate: dict[str, Any],
    owner: User,
    request_data: dict[str, Any] | None,
) -> dict[str, str]:
    _errors = {}
    channels = capture_candidate.get("channels")
    if not channels and request_data:
        channels = request_data.get("channels")
    if channels:
        cap_qs: QuerySet[Capture] = Capture.objects.filter(
            top_level_dir=capture_candidate.get("top_level_dir"),
            capture_type=CaptureType.DigitalRF,
            is_deleted=False,
            owner=owner,
        )
        for existing_capture in cap_qs:
            existing_channels = existing_capture.channels
            if any(channel in existing_channels for channel in channels):
                already_in_use_msg = (
                    "These channels and top level directory are already in use by "
                    f"another capture: {existing_capture.pk}"
                )
                _errors["drf_unique_channels_and_tld"] = already_in_use_msg
                break
    return _errors


def _check_rh_constraints(
    capture_candidate: dict[str, Any],
    owner: User,
) -> dict[str, str]:
    _errors = {}
    scan_group: str | None = capture_candidate.get("scan_group")
    cap_qs: QuerySet[Capture] = Capture.objects.filter(
        scan_group=scan_group,
        capture_type=CaptureType.RadioHound,
        is_deleted=False,
        owner=owner,
    )
    if scan_group is not None and cap_qs.exists():
        conflicting_capture = cap_qs.first()
        assert conflicting_capture is not None, "QuerySet should not be empty here."
        _errors["rh_unique_scan_group"] = (
            f"This scan group is already in use by "
            f"another capture: {conflicting_capture.pk}"
        )
    return _errors


def _check_capture_creation_constraints(
    capture_candidate: dict[str, Any],
    owner: User,
    request_data: dict[str, Any] | None = None,
) -> None:
    """Check constraints for capture creation. Raise ValueError if any are violated."""
    capture_type = capture_candidate.get("capture_type")
    _errors: dict[str, str] = {}

    # Required fields
    _errors.update(_check_required_fields(capture_candidate))
    if _errors:
        msg = "Capture creation constraints violated:" + "".join(
            f"\n\t{rule}: {error}" for rule, error in _errors.items()
        )
        log.warning(msg)
        raise AssertionError(msg)

    # DigitalRF constraints
    if capture_type == CaptureType.DigitalRF:
        _errors.update(_check_drf_constraints(capture_candidate, owner, request_data))
    # RadioHound constraints
    if capture_type == CaptureType.RadioHound:
        _errors.update(_check_rh_constraints(capture_candidate, owner))

    if _errors:
        msg = "Capture creation constraints violated:"
        for rule, error in _errors.items():
            msg += f"\n\t{rule}: {error}"
        log.warning(msg)
        raise ValueError(msg)
