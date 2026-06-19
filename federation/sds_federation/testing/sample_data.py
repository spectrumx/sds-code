"""Fixed UUIDs and sample export docs for isolated sync tests."""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from uuid import UUID

from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc

# Stable id used across tests and manual simulations.
TEST_DATASET_UUID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
TEST_CAPTURE_UUID = UUID("bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee")

SIMULATED_REDIS_TIMESTAMP = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)


def simulated_dataset_redis_payload(
    *,
    uuid: UUID = TEST_DATASET_UUID,
    event_type: str = "updated",
) -> dict[str, str]:
    """Gateway-compatible federation:events JSON (before Redis serializes it)."""
    return {
        "event_type": event_type,
        "item_type": "dataset",
        "uuid": str(uuid),
        "timestamp": SIMULATED_REDIS_TIMESTAMP.isoformat(),
    }


def sample_federated_dataset_doc(
    *,
    uuid: UUID = TEST_DATASET_UUID,
    site_name: str = "testsite",
) -> FederatedDatasetDoc:
    return FederatedDatasetDoc(
        uuid=uuid,
        name="Simulated public dataset",
        status="final",
        status_display="Final",
        site_name=site_name,
        is_public=True,
        owner_name="Test Owner",
    )


def sample_federated_capture_doc(
    *,
    uuid: UUID = TEST_CAPTURE_UUID,
    site_name: str = "testsite",
) -> FederatedCaptureDoc:
    return FederatedCaptureDoc(
        uuid=uuid,
        name="Simulated capture",
        capture_type="drf",
        channel="0",
        site_name=site_name,
    )
