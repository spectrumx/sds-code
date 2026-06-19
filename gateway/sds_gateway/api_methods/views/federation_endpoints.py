"""Federation export API (sync service → gateway, Postgres public metadata)."""

from __future__ import annotations

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.helpers.compile_federated_data import (
    compile_federated_capture_doc,
)
from sds_gateway.api_methods.helpers.compile_federated_data import (
    compile_federated_dataset_doc,
)
from sds_gateway.api_methods.helpers.compile_federated_data import (
    is_federation_exportable_capture,
)
from sds_gateway.api_methods.helpers.compile_federated_data import (
    is_federation_exportable_dataset,
)
from sds_gateway.api_methods.helpers.compile_federated_data import (
    public_captures_queryset,
)
from sds_gateway.api_methods.helpers.compile_federated_data import (
    public_datasets_queryset,
)
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.federation.permissions import IsFederationInternalExportClient
from sds_gateway.api_methods.federation.permissions import IsFederationOperational
from sds_gateway.api_methods.permissions import IsFederationSyncKey


@extend_schema(exclude=True)
class FederationViewSet(ViewSet):
    """Internal export endpoints for the federation sync service."""

    authentication_classes = [APIKeyAuthentication]
    permission_classes = [
        IsFederationSyncKey,
        IsFederationOperational,
        IsFederationInternalExportClient,
    ]

    @action(detail=False, methods=["get"], url_path="export/datasets")
    def export_datasets_list(self, request: Request) -> Response:
        """List all public finalized datasets for federation bootstrap."""
        datasets = public_datasets_queryset()
        return Response(
            [compile_federated_dataset_doc(dataset) for dataset in datasets],
        )

    @action(
        detail=False,
        methods=["get"],
        url_path=r"export/datasets/(?P<pk>[^/.]+)",
    )
    def export_dataset_detail(self, request: Request, pk: str | None = None) -> Response:
        """Return one public dataset for sync after a local Redis event."""
        dataset = get_object_or_404(Dataset, pk=pk, is_deleted=False)
        if not is_federation_exportable_dataset(dataset):
            return Response(
                {"detail": "Dataset is not available for federation export."},
                status=404,
            )
        return Response(compile_federated_dataset_doc(dataset))

    @action(detail=False, methods=["get"], url_path="export/captures")
    def export_captures_list(self, request: Request) -> Response:
        """List all public captures for federation bootstrap."""
        captures = public_captures_queryset()
        return Response(
            [compile_federated_capture_doc(capture) for capture in captures],
        )

    @action(
        detail=False,
        methods=["get"],
        url_path=r"export/captures/(?P<pk>[^/.]+)",
    )
    def export_capture_detail(self, request: Request, pk: str | None = None) -> Response:
        """Return one public capture for sync after a local Redis event."""
        capture = get_object_or_404(Capture, pk=pk, is_deleted=False)
        if not is_federation_exportable_capture(capture):
            return Response(
                {"detail": "Capture is not available for federation export."},
                status=404,
            )
        return Response(compile_federated_capture_doc(capture))
