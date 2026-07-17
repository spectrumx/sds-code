"""Build federation export payloads and fed-* OpenSearch helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING
from typing import Any

from django.conf import settings
from loguru import logger as log
from opensearchpy import exceptions as os_exceptions
from opensearchpy.exceptions import NotFoundError

from sds_gateway.api_methods.federation.fed_index import federated_doc_id
from sds_gateway.api_methods.federation.fed_index import index_for_item_type
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import ItemType
from sds_gateway.api_methods.serializers.capture_serializers import (
    CaptureFederationSerializer,
)
from sds_gateway.api_methods.serializers.dataset_serializers import (
    DatasetFederationSerializer,
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.utils.relationship_utils import get_capture_datasets

if TYPE_CHECKING:
    from uuid import UUID

    from django.db.models import QuerySet


def federation_site_name() -> str:
    return getattr(settings, "FEDERATION_SITE_NAME", "").strip()


def capture_in_published_dataset(capture: Capture) -> bool:
    exportable_datasets = get_capture_datasets(
        capture,
        include_deleted=False
    ).federation_exportable()
    return exportable_datasets.exists()


def capture_in_other_published_datasets(
    capture: Capture,
    *,
    exclude_dataset_id: UUID,
) -> bool:
    exportable_datasets = get_capture_datasets(
        capture,
        include_deleted=False
    ).federation_exportable()
    return exportable_datasets.exclude(uuid=exclude_dataset_id).exists()


def compile_federated_dataset_doc(dataset: Dataset) -> dict[str, Any]:
    site_name = federation_site_name()
    return DatasetFederationSerializer(
        dataset,
        context={"site_name": site_name},
    ).data


def compile_federated_capture_doc(capture: Capture) -> dict[str, Any]:
    site_name = federation_site_name()
    return CaptureFederationSerializer(
        capture,
        context={"site_name": site_name},
    ).data


def compile_federated_doc(
    instance: Dataset | Capture,
) -> dict[str, Any]:
    if isinstance(instance, Dataset):
        return compile_federated_dataset_doc(instance)
    return compile_federated_capture_doc(instance)


def get_federated_export_doc_by_uuid(
    *,
    asset_type: ItemType,
    asset_uuid: UUID,
    site_name: str | None = None,
) -> dict[str, Any] | None:
    """Return indexed federation export body for this site, or None if missing."""
    resolved_site = (site_name or federation_site_name()).strip()
    if not resolved_site:
        return None
    client = get_opensearch_client()
    index = index_for_item_type(asset_type)
    doc_id = federated_doc_id(
        site_name=resolved_site,
        uuid=asset_uuid,
    )
    try:
        response = client.get(index=index, id=doc_id)
    except NotFoundError:
        return None
    except os_exceptions.OpenSearchException as exc:
        log.warning(
            f"Federation fed doc lookup failed for {asset_type.value} {asset_uuid}: {exc}",
        )
        return None
    source = response.get("_source")
    if not isinstance(source, dict):
        return None
    return source


def fed_doc_exists(
    *,
    asset_type: ItemType,
    site_name: str,
    instance: Dataset | Capture,
) -> bool:
    return (
        get_federated_export_doc_by_uuid(
            asset_type=asset_type,
            asset_uuid=instance.uuid,
            site_name=site_name,
        )
        is not None
    )


def public_datasets_queryset() -> QuerySet[Dataset]:
    return (
        Dataset.objects.federation_exportable()
        .prefetch_related("keywords", "owner")
        .order_by("-updated_at")
    )


def public_captures_queryset() -> QuerySet[Capture]:
    return (
        Capture.objects.filter(is_deleted=False)
        .filter(datasets__in=Dataset.objects.federation_exportable())
        .distinct()
        .order_by("-updated_at")
    )
