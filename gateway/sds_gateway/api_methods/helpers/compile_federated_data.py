"""Build federation export payloads (RFC fed-* index shape)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import DatasetStatus
from sds_gateway.api_methods.serializers.capture_serializers import (
    CaptureFederationSerializer,
)
from sds_gateway.api_methods.serializers.dataset_serializers import (
    DatasetFederationSerializer,
)

if TYPE_CHECKING:
    from django.db.models import QuerySet


def federation_site_name() -> str:
    return getattr(settings, "FEDERATION_SITE_NAME", "").strip()


def public_datasets_queryset() -> QuerySet[Dataset]:
    return (
        Dataset.objects.filter(
            status=DatasetStatus.FINAL,
            is_public=True,
            is_deleted=False,
        )
        .prefetch_related("keywords", "owner")
        .order_by("-updated_at")
    )


def public_captures_queryset() -> QuerySet[Capture]:
    return Capture.objects.filter(is_public=True, is_deleted=False).order_by(
        "-updated_at",
    )


def is_federation_exportable_dataset(dataset: Dataset) -> bool:
    return (
        not dataset.is_deleted
        and dataset.is_public
        and dataset.status == DatasetStatus.FINAL
    )


def is_federation_exportable_capture(capture: Capture) -> bool:
    return not capture.is_deleted and capture.is_public


def compile_federated_dataset_doc(dataset: Dataset) -> dict[str, Any]:
    """Serialize a public dataset for federation sync / OpenSearch."""
    site_name = federation_site_name()
    federation_data = DatasetFederationSerializer(
        dataset,
        context={"site_name": site_name},
    )
    return federation_data.data


def compile_federated_capture_doc(capture: Capture) -> dict[str, Any]:
    """Serialize a public capture for federation sync / OpenSearch."""
    site_name = federation_site_name()
    federation_data = CaptureFederationSerializer(
        capture,
        context={"site_name": site_name},
    )
    return federation_data.data
