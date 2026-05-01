"""Dataset operations endpoints for the SDS Gateway API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.dataset_serializers import DatasetGetSerializer
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.utils.asset_access_control import check_if_shared
from sds_gateway.api_methods.utils.asset_access_control import (
    revoke_share_permissions as revoke_item_share_permissions,
)
from sds_gateway.api_methods.utils.dataset_manifest_filters import (
    filter_dataset_files_queryset,
)
from sds_gateway.api_methods.utils.dataset_manifest_filters import (
    parse_capture_uuid_query,
)
from sds_gateway.api_methods.utils.dataset_manifest_filters import (
    parse_top_level_dir_query,
)
from sds_gateway.api_methods.utils.relationship_utils import get_dataset_artifact_files
from sds_gateway.api_methods.utils.relationship_utils import (
    get_dataset_files_including_captures,
)
from sds_gateway.api_methods.views.file_endpoints import FilePagination
from sds_gateway.users.models import User

if TYPE_CHECKING:
    from uuid import UUID

    from django.db.models import QuerySet
    from rest_framework.request import Request


def _truthy_query_param(raw: str | None) -> bool:
    if raw is None:
        return False
    return raw.strip().lower() in ("1", "true", "yes")


class DatasetViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_file_objects(
        self,
        dataset: Dataset,
        *,
        artifacts_only: bool = False,
    ) -> QuerySet[File]:
        """Get all files associated with a dataset."""
        if artifacts_only:
            return get_dataset_artifact_files(dataset, include_deleted=False)
        return get_dataset_files_including_captures(dataset, include_deleted=False)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="Dataset UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            200: OpenApiResponse(
                description=("Dataset metadata, captures, and direct artifact files"),
            ),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not Found"),
        },
        description=(
            "Return dataset metadata with captures (one row per logical capture, "
            "including composite multi-channel) and artifact files on the dataset."
        ),
        summary="Retrieve Dataset",
    )
    def retrieve(self, request: Request, pk: str | None = None) -> Response:
        """Return serialized dataset including captures and direct (artifact) files."""
        if pk is None:
            return Response(
                {"detail": "Dataset UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_dataset = get_object_or_404(
            Dataset,
            pk=pk,
            is_deleted=False,
        )

        assert isinstance(request.user, User), (
            "Expected request.user to be an instance of the custom User model"
        )
        if not user_has_access_to_item(
            request.user, target_dataset.uuid, ItemType.DATASET
        ):
            return Response(
                {"detail": "You do not have permission to access this dataset."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = DatasetGetSerializer(
            target_dataset,
            context={"request": request},
        )
        return Response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="Dataset UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
            OpenApiParameter(
                name="page",
                description="Page number for pagination.",
                required=False,
                type=int,
                location=OpenApiParameter.QUERY,
                default=1,
            ),
            OpenApiParameter(
                name="page_size",
                description="Number of items per page.",
                required=False,
                type=int,
                location=OpenApiParameter.QUERY,
                default=FilePagination.page_size,
            ),
            OpenApiParameter(
                name="capture",
                description=(
                    "Only include files linked to this capture UUID "
                    "(repeat param or comma-separated). OR with top_level_dir."
                ),
                required=False,
                type=str,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="top_level_dir",
                description=(
                    "Only include files whose directory is this path or under it "
                    "(repeat param or comma-separated). Normalized like capture "
                    "top_level_dir."
                ),
                required=False,
                type=str,
                location=OpenApiParameter.QUERY,
            ),
            OpenApiParameter(
                name="artifact_only",
                description="Only include artifact files (not capture-linked files).",
                required=False,
                type=bool,
                location=OpenApiParameter.QUERY,
            ),
        ],
        responses={
            200: OpenApiResponse(description="Dataset file listing"),
            400: OpenApiResponse(description="Bad Request"),
            403: OpenApiResponse(description="Forbidden"),
            404: OpenApiResponse(description="Not Found"),
        },
        description=(
            "Get a manifest of files in the dataset, separated by "
            "captures and artifacts. "
            "This allows efficient downloading using the existing download "
            "infrastructure."
        ),
        summary="Get Dataset Files Manifest",
    )
    @action(detail=True, methods=["get"], url_path="files", url_name="files")
    def get_dataset_files(self, request: Request, pk: str | None = None) -> Response:
        """Get a paginated list of files in the dataset to be downloaded."""

        if pk is None:
            return Response(
                {"detail": "Dataset UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        target_dataset = get_object_or_404(
            Dataset,
            pk=pk,
            is_deleted=False,
        )

        assert isinstance(request.user, User), (
            "Expected request.user to be an instance of the custom User model"
        )
        if not user_has_access_to_item(
            request.user, target_dataset.uuid, ItemType.DATASET
        ):
            return Response(
                {"detail": "You do not have permission to access this dataset."},
                status=status.HTTP_403_FORBIDDEN,
            )

        artifacts_only = _truthy_query_param(request.GET.get("artifacts_only"))

        # Get all files associated with this dataset
        dataset_files = self._get_file_objects(
            target_dataset,
            artifacts_only=artifacts_only,
        )

        if not dataset_files.exists():
            return Response(
                {"detail": "No files found in dataset."},
                status=status.HTTP_404_NOT_FOUND,
            )

        capture_uuids: list[UUID] = []
        if not artifacts_only:
            try:
                capture_uuids = parse_capture_uuid_query(request)
            except ValueError as err:
                return Response(
                    {"detail": str(err)},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        top_level_dir_prefixes = parse_top_level_dir_query(request)
        if capture_uuids or top_level_dir_prefixes:
            dataset_files = filter_dataset_files_queryset(
                dataset_files,
                capture_uuids=capture_uuids,
                top_level_dir_prefixes=top_level_dir_prefixes,
            )

        # Order and deduplicate files by path and created_at; avoid N+1 on captures
        ordered_files = (
            dataset_files.order_by("-created_at")
            .select_related(
                "capture",
                "owner",
            )
            .prefetch_related("captures", "datasets")
        )
        paginator = FilePagination()
        paginated_files = paginator.paginate_queryset(ordered_files, request=request)

        # Serialize the files
        serializer = FileGetSerializer(paginated_files, many=True)

        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="Dataset UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            204: OpenApiResponse(description="No Content"),
            404: OpenApiResponse(description="Not Found"),
        },
        description="Revoke all share permissions for a dataset.",
        summary="Revoke Dataset Share Permissions",
    )
    @action(
        detail=True,
        methods=["put"],
        url_path="revoke-share-permissions",
        url_name="revoke-share-permissions",
    )
    def revoke_share_permissions(
        self, request: Request, pk: str | None = None
    ) -> Response:
        """Revoke all share permissions for a dataset."""
        if pk is None:
            return Response(
                {"detail": "Dataset UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_dataset = get_object_or_404(
            Dataset,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        revoked = revoke_item_share_permissions(
            item_type=ItemType.DATASET,
            item_uuid=target_dataset.uuid,
        )

        if not revoked:
            return Response(
                {"detail": "Failed to revoke share permissions."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            status=status.HTTP_200_OK,
            data={
                "message": "Share permissions revoked successfully",
            },
        )

    @extend_schema(
        parameters=[
            OpenApiParameter(
                name="id",
                description="Dataset UUID",
                required=True,
                type=str,
                location=OpenApiParameter.PATH,
            ),
        ],
        responses={
            204: OpenApiResponse(description="No Content"),
            404: OpenApiResponse(description="Not Found"),
        },
        description="Delete a dataset from the server.",
        summary="Delete Dataset",
    )
    def destroy(self, request: Request, pk: str | None = None) -> Response:
        """Delete a dataset from the server."""
        if pk is None:
            return Response(
                {"detail": "Dataset UUID is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        target_dataset = get_object_or_404(
            Dataset,
            pk=pk,
            owner=request.user,
            is_deleted=False,
        )

        is_shared = check_if_shared(target_dataset.uuid, ItemType.DATASET)

        if is_shared:
            return Response(
                {"detail": "Dataset is shared and cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        target_dataset.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
