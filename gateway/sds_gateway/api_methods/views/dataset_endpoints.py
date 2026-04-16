"""Dataset operations endpoints for the SDS Gateway API."""

from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import OpenApiResponse
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.deletion_policy_helpers import (
    bypass_share_guard_from_request,
    resolve_asset_shared_deletion,
)
from sds_gateway.api_methods.utils.asset_access_control import check_if_shared
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import UserSharePermission
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.utils.relationship_utils import (
    get_dataset_files_including_captures,
)
from sds_gateway.api_methods.views.file_endpoints import FilePagination
from sds_gateway.users.models import User


class DatasetViewSet(ViewSet):
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]

    def _get_file_objects(self, dataset: Dataset) -> QuerySet[File]:
        """Get all files associated with a dataset."""
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

        # Get all files associated with this dataset
        dataset_files = self._get_file_objects(target_dataset)

        if not dataset_files.exists():
            return Response(
                {"detail": "No files found in dataset."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Order and deduplicate files by path and created_at
        ordered_files = dataset_files.order_by("-created_at")
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
    @action(detail=True, methods=["put"], url_path="revoke-share-permissions", url_name="revoke-share-permissions")
    def revoke_share_permissions(self, request: Request, pk: str | None = None) -> Response:
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
        
        revoked = revoke_share_permissions(
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
    @action(detail=True, methods=["delete"], url_path="", url_name="delete")
    def delete(self, request: Request, pk: str | None = None) -> Response:
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
        
        is_shared, _ = check_if_shared(
            target_dataset.uuid, ItemType.DATASET
        )
        
        if is_shared:
            return Response(
                {"detail": "Dataset is shared and cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )

        target_dataset.soft_delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

