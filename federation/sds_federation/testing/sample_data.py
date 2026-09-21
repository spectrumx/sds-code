"""Fixed UUIDs and sample export docs for isolated sync tests.

OpenSearch mappings live in :mod:`sds_opensearch_query.mapping` (RFC §6). Indexed
``fed-datasets`` / ``fed-captures`` documents use these top-level fields (plus
``dynamic: true`` for export keys not listed here). ``federation_event_at`` is
stamped at index time by
:func:`sds_opensearch_query.index_write.index_federated_document`, not by the
gateway export payload.

**fed-datasets** — keys from ``RFC_FED_DATASET_PROPERTIES``:

- ``uuid`` (keyword)
- ``site_name`` (keyword) — peer FQDN (``federation.toml`` ``[site].fqdn``),
  not short name
- ``name`` (text + keyword subfield)
- ``version`` (integer)
- ``description``, ``abstract`` (text)
- ``keywords`` (keyword)
- ``owner_name``, ``status`` (keyword)
- ``is_public``, ``is_deleted`` (boolean)
- ``created_at``, ``updated_at``, ``federation_event_at`` (date)
- ``size`` (long)
- ``capture_count``, ``capture_file_count``, ``artifact_file_count`` (integer)
- ``url`` (keyword) — canonical dataset URL on the owning site

Webhook/export models (:class:`~sds_federation.schemas.webhooks.FederatedDatasetDoc`)
also carry serializer fields (e.g. ``status_display``, ``doi``, ``authors``) that may
be stored when present but are not in the RFC search mapping above.

**fed-captures** — keys from ``RFC_FED_CAPTURE_PROPERTIES``:

- ``uuid``, ``site_name`` (keyword; ``site_name`` = peer FQDN)
- ``name`` (text + keyword subfield)
- ``capture_type``, ``channel``, ``scan_group``, ``top_level_dir``,
  ``owner_name`` (keyword)
- ``file_count`` (integer), ``size`` (long)
- ``created_at``, ``updated_at``, ``federation_event_at`` (date)
- ``is_deleted`` (boolean)
- ``capture_props``, ``search_props`` (nested, dynamic) — see gateway
  ``metadata_schemas.py`` for prop shapes
- ``public_dataset_ids`` (keyword)
- ``url`` (keyword) — canonical capture URL on the owning site
"""

from __future__ import annotations

from datetime import UTC
from datetime import datetime
from uuid import UUID

from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc

# Stable ids used across tests and manual simulations.
TEST_DATASET_UUID = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
TEST_CAPTURE_UUID = UUID("bbbbbbbb-bbbb-cccc-dddd-eeeeeeeeeeee")
TEST_SCAN_GROUP_UUID = UUID("cccccccc-bbbb-cccc-dddd-eeeeeeeeeeee")

SIMULATED_REDIS_TIMESTAMP = datetime(2026, 6, 11, 12, 0, 0, tzinfo=UTC)
_SAMPLE_DOC_TIMESTAMP = SIMULATED_REDIS_TIMESTAMP.isoformat()


def simulated_dataset_redis_payload(
    *,
    uuid: UUID = TEST_DATASET_UUID,
) -> dict[str, str]:
    """Gateway-compatible federation:events JSON (before Redis serializes it)."""
    return {
        "item_type": "dataset",
        "uuid": str(uuid),
        "timestamp": SIMULATED_REDIS_TIMESTAMP.isoformat(),
    }


def sample_federated_dataset_doc(
    *,
    uuid: UUID = TEST_DATASET_UUID,
    site_name: str = "localhost",
) -> FederatedDatasetDoc:
    """Build a :class:`FederatedDatasetDoc` with every RFC mapped field set.

    Sets all ``RFC_FED_DATASET_PROPERTIES`` keys that belong on export/webhook
    payloads. ``federation_event_at`` is omitted here (added when indexing).
    """
    return FederatedDatasetDoc(
        uuid=uuid,
        site_name=site_name,
        name="Simulated public dataset",
        version=1,
        description="Sample dataset description for federation tests.",
        abstract="Sample abstract.",
        keywords=["federation", "test"],
        owner_name="Test Owner",
        status="final",
        status_display="Final",
        is_public=True,
        is_deleted=False,
        created_at=_SAMPLE_DOC_TIMESTAMP,
        updated_at=_SAMPLE_DOC_TIMESTAMP,
        size=1024,
        capture_count=1,
        capture_file_count=10,
        artifact_file_count=2,
        url=f"https://{site_name}/datasets/{uuid}",
    )


def sample_federated_capture_doc(
    *,
    uuid: UUID = TEST_CAPTURE_UUID,
    site_name: str = "localhost",
    dataset_uuid: UUID = TEST_DATASET_UUID,
) -> FederatedCaptureDoc:
    """Build a :class:`FederatedCaptureDoc` with every RFC mapped field set.

    ``capture_props`` / ``search_props`` default to empty dicts (tests assert that
    shape); nested keys follow gateway metadata schemas when you need them.
    ``federation_event_at`` is omitted here (added when indexing).
    """
    return FederatedCaptureDoc(
        uuid=uuid,
        site_name=site_name,
        name="Simulated capture",
        capture_type="drf",
        channel="0",
        top_level_dir="/data/captures/simulated",
        owner_name="Test Owner",
        file_count=10,
        size=2048,
        created_at=_SAMPLE_DOC_TIMESTAMP,
        updated_at=_SAMPLE_DOC_TIMESTAMP,
        is_deleted=False,
        capture_props={},
        search_props={},
        public_dataset_ids=[str(dataset_uuid)],
        url=f"https://{site_name}/captures/{uuid}",
    )
