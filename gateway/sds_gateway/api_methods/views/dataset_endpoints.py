"""Dataset operations endpoints for the SDS Gateway API."""

from django.db.models import QuerySet
from django.http import JsonResponse
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
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.models import user_has_access_to_item
from sds_gateway.api_methods.serializers.file_serializers import FileGetSerializer
from sds_gateway.api_methods.utils.relationship_utils import (
    get_dataset_files_including_captures,
)
from sds_gateway.api_methods.views.file_endpoints import FilePagination


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
    def get_dataset_files(
        self, request: Request, pk: str | None = None
    ) -> JsonResponse:
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
