"""Federation export API (sync service reads local fed-* OpenSearch docs)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from drf_spectacular.utils import extend_schema
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.viewsets import ViewSet

if TYPE_CHECKING:
    from rest_framework.request import Request

from sds_gateway.api_methods.authentication import APIKeyAuthentication
from sds_gateway.api_methods.federation.compile_federated_data import (
    compile_federated_capture_doc,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    compile_federated_dataset_doc,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    get_federated_export_doc_by_uuid,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    public_captures_queryset,
)
from sds_gateway.api_methods.federation.compile_federated_data import (
    public_datasets_queryset,
)
from sds_gateway.api_methods.federation.permissions import (
    IsFederationInternalExportClient,
)
from sds_gateway.api_methods.federation.permissions import IsFederationOperational
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.permissions import IsFederationSyncKey


def _federation_export_uuid(pk: str | None) -> UUID:
    if not pk:
        raise NotFound()
    try:
        return UUID(pk)
    except ValueError as exc:
        raise NotFound() from exc


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
    def export_dataset_detail(
        self, request: Request, pk: str | None = None
    ) -> Response:
        """Return one indexed dataset doc (post-signal); 404 if not in fed-datasets."""
        asset_uuid = _federation_export_uuid(pk)
        body = get_federated_export_doc_by_uuid(
            asset_type=ItemType.DATASET,
            asset_uuid=asset_uuid,
        )
        if body is None:
            raise NotFound()
        return Response(body)

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
    def export_capture_detail(
        self, request: Request, pk: str | None = None
    ) -> Response:
        """Return one indexed capture doc (post-signal); 404 if not in fed-captures."""
        asset_uuid = _federation_export_uuid(pk)
        body = get_federated_export_doc_by_uuid(
            asset_type=ItemType.CAPTURE,
            asset_uuid=asset_uuid,
        )
        if body is None:
            raise NotFound()
        return Response(body)
