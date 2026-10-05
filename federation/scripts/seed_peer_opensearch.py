#!/usr/bin/env python3
"""Seed dummy federated docs into a peer OpenSearch (no gateway).

Use for peer→main backfill / list-* tests. ``site_name`` must be the peer FQDN
(matches federation.toml ``[site].fqdn``).

Examples::

  # Local peer stack (OpenSearch on host :9201) — one dataset + one capture
  uv run python scripts/seed_peer_opensearch.py \\
    --opensearch-url http://localhost:9201 \\
    --site-name peer.local

  # Many datasets and linked captures (deterministic UUIDs for re-runs)
  uv run python scripts/seed_peer_opensearch.py \\
    --opensearch-url http://localhost:9201 \\
    --site-name peer.local \\
    --datasets 20 --captures-per-dataset 5 --seed 42

  # Remote peer (notify main site via dataset/capture-updated webhooks)
  FEDERATION_CONFIG_PATH=./federation.peer.toml uv run python scripts/seed_peer_opensearch.py \\
    --opensearch-url http://localhost:9200 \\
    --site-name sds-fed1.crc.nd.edu \\
    --datasets 3 --captures-per-dataset 3 --seed 1 --notify-peers

  # Remote peer after port-forward / public OS URL
  uv run python scripts/seed_peer_opensearch.py \\
    --opensearch-url https://peer-os.example:9200 \\
    --site-name peer.example.com \\
    --user admin --password secret
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from datetime import UTC
from datetime import datetime
from datetime import timedelta

from opensearchpy import OpenSearch
from sds_federation.models import load_federation_config
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.schemas.webhooks import AssetUpdatedWebhook
from sds_federation.schemas.webhooks import FederatedCaptureDoc
from sds_federation.schemas.webhooks import FederatedDatasetDoc
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.services.fed_index import ensure_fed_indices
from sds_federation.services.peer_http import build_peer_http_client
from sds_federation.services.peer_sync import push_asset_updated_to_peers
from sds_federation.testing.sample_data import TEST_CAPTURE_UUID
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_capture_doc
from sds_federation.testing.sample_data import sample_federated_capture_search_props
from sds_federation.testing.sample_data import sample_federated_dataset_doc
from sds_federation.testing.sample_data import sample_federated_drf_capture_props

_PEER_SEED_NAMESPACE = uuid.UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")
# Capture list UI slider range (GHz); seeded center frequencies stay inside this band.
_PEER_SEED_FREQ_MIN_GHZ = 0.5
_PEER_SEED_FREQ_STEP_GHZ = 0.4


def _seed_capture_center_frequency_hz(ds_index: int, cap_index: int) -> float:
    """Deterministic center frequency (Hz) within the capture-list filter slider."""
    ghz = _PEER_SEED_FREQ_MIN_GHZ + (ds_index + cap_index) * _PEER_SEED_FREQ_STEP_GHZ
    ghz = min(ghz, 9.5)
    return ghz * 1e9


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--opensearch-url",
        default="http://localhost:9201",
        help="Peer OpenSearch base URL (local peer compose publishes :9201)",
    )
    p.add_argument(
        "--site-name",
        default="peer.local",
        help="Peer FQDN written into docs (must match toml [site].fqdn)",
    )
    p.add_argument(
        "--datasets",
        type=int,
        default=1,
        metavar="N",
        help="Number of dataset documents to index (default: 1)",
    )
    p.add_argument(
        "--captures-per-dataset",
        type=int,
        default=1,
        metavar="N",
        help="Captures to create per dataset, linked via public_dataset_ids (default: 1)",
    )
    p.add_argument(
        "--name-prefix",
        default="Peer seed",
        help="Prefix for generated asset names",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="INT",
        help="Deterministic UUIDs via uuid5 (re-run safe); omit for random uuid4",
    )
    p.add_argument(
        "--dataset-uuid",
        default=None,
        help="UUID for the sole dataset when --datasets is 1 (default: stable test id)",
    )
    p.add_argument(
        "--capture-uuid",
        default=None,
        help=(
            "UUID for the sole capture when --datasets and --captures-per-dataset "
            "are both 1 (default: stable test id)"
        ),
    )
    p.add_argument("--user", default="", help="Optional basic-auth user")
    p.add_argument("--password", default="", help="Optional basic-auth password")
    p.add_argument(
        "--use-ssl",
        action="store_true",
        help="Force SSL client (also inferred from https:// URL)",
    )
    p.add_argument(
        "--notify-peers",
        action="store_true",
        help=(
            "POST dataset/capture-updated webhooks to each [[peers]] entry in "
            "federation config (FEDERATION_CONFIG_PATH); mirrors sync Redis fan-out"
        ),
    )
    return p.parse_args()


def _client_from_url(args: argparse.Namespace) -> OpenSearch:
    url = args.opensearch_url.rstrip("/")
    use_ssl = args.use_ssl or url.startswith("https://")
    # OpenSearch client wants host/port; parse simply.
    without_scheme = url.split("://", 1)[-1]
    host_port, _, _path = without_scheme.partition("/")
    if ":" in host_port:
        host, port_s = host_port.rsplit(":", 1)
        port = int(port_s)
    else:
        host = host_port
        port = 443 if use_ssl else 9200

    kwargs: dict = {
        "hosts": [{"host": host, "port": port}],
        "use_ssl": use_ssl,
        "verify_certs": False,
        "ssl_show_warn": False,
    }
    if args.user:
        kwargs["http_auth"] = (args.user, args.password)
    return OpenSearch(**kwargs)


def _make_uuid(
    *,
    site: str,
    seed: int | None,
    kind: str,
    parts: tuple[object, ...] = (),
) -> uuid.UUID:
    if seed is not None:
        name = ":".join((str(seed), site, kind, *(str(p) for p in parts)))
        return uuid.uuid5(_PEER_SEED_NAMESPACE, name)
    return uuid.uuid4()


def _dataset_uuid_for_index(
    args: argparse.Namespace,
    site: str,
    index: int,
) -> uuid.UUID:
    if args.datasets == 1 and index == 0 and args.dataset_uuid is not None:
        return uuid.UUID(args.dataset_uuid)
    if (
        args.datasets == 1
        and index == 0
        and args.seed is None
        and args.dataset_uuid is None
    ):
        return TEST_DATASET_UUID
    return _make_uuid(site=site, seed=args.seed, kind="dataset", parts=(index,))


def _capture_uuid_for_index(
    args: argparse.Namespace,
    site: str,
    dataset_index: int,
    capture_index: int,
) -> uuid.UUID:
    if (
        args.datasets == 1
        and args.captures_per_dataset == 1
        and dataset_index == 0
        and capture_index == 0
        and args.capture_uuid is not None
    ):
        return uuid.UUID(args.capture_uuid)
    if (
        args.datasets == 1
        and args.captures_per_dataset == 1
        and dataset_index == 0
        and capture_index == 0
        and args.seed is None
        and args.capture_uuid is None
    ):
        return TEST_CAPTURE_UUID
    return _make_uuid(
        site=site,
        seed=args.seed,
        kind="capture",
        parts=(dataset_index, capture_index),
    )


def _dataset_authors(prefix: str, ds_index: int) -> list[dict[str, str]]:
    """Gateway export shape: list of {name, orcid_id} dicts."""
    return [
        {"name": f"{prefix} author {ds_index}", "orcid_id": ""},
        {"name": f"{prefix} co-author {ds_index}", "orcid_id": ""},
    ]


def _validate_counts(args: argparse.Namespace) -> str | None:
    if args.datasets < 0:
        return "--datasets must be >= 0"
    if args.captures_per_dataset < 0:
        return "--captures-per-dataset must be >= 0"
    if args.datasets == 0 and args.captures_per_dataset > 0:
        return "--captures-per-dataset requires --datasets >= 1"
    if args.datasets != 1 and (args.dataset_uuid or args.capture_uuid):
        return "--dataset-uuid/--capture-uuid only apply when seeding a single pair"
    return None


async def _notify_peers_for_assets(
    site: str,
    assets: list[
        tuple[
            datetime,
            FederatedDatasetDoc | FederatedCaptureDoc,
            AssetTypeEnum,
        ]
    ],
) -> None:
    """Fan out AssetUpdatedWebhook payloads the same way local sync does after Redis."""
    config = load_federation_config()
    if not config.peers:
        print(
            "WARNING: --notify-peers but federation config has no [[peers]]",
            file=sys.stderr,
        )
        return
    peer_names = ", ".join(peer.name for peer in config.peers)
    async with build_peer_http_client() as http:
        for event_at, asset, asset_type in assets:
            payload = AssetUpdatedWebhook(
                timestamp=event_at,
                site_name=site,
                asset=asset,
                asset_type=asset_type,
            )
            await push_asset_updated_to_peers(http, config, payload, registry=None)
    print(f"Notified peer(s) [{peer_names}] for {len(assets)} asset webhook(s)")


def main() -> int:
    args = _parse_args()
    site = args.site_name.strip()
    if not site:
        print("ERROR: --site-name is required", file=sys.stderr)
        return 1
    count_err = _validate_counts(args)
    if count_err:
        print(f"ERROR: {count_err}", file=sys.stderr)
        return 1

    client = _client_from_url(args)
    ensure_fed_indices(client)
    indexer = FederatedAssetIndexer(client)
    base_event_at = datetime.now(UTC)
    prefix = args.name_prefix.strip() or "Peer seed"
    event_step = 0
    seeded_datasets = 0
    seeded_captures = 0
    notify_queue: list[
        tuple[
            datetime,
            FederatedDatasetDoc | FederatedCaptureDoc,
            AssetTypeEnum,
        ]
    ] = []

    def next_event_at() -> datetime:
        nonlocal event_step
        event_at = base_event_at + timedelta(seconds=event_step)
        event_step += 1
        return event_at

    for ds_index in range(args.datasets):
        dataset_uuid = _dataset_uuid_for_index(args, site, ds_index)
        event_at = next_event_at()
        iso = event_at.isoformat()
        dataset = sample_federated_dataset_doc(uuid=dataset_uuid, site_name=site)
        dataset = dataset.model_copy(
            update={
                "name": f"{prefix} dataset {ds_index}",
                "is_public": True,
                "status": "final",
                "status_display": "Final",
                "capture_count": args.captures_per_dataset,
                "authors": _dataset_authors(prefix, ds_index),
                "created_at": iso,
                "updated_at": iso,
            },
        )
        indexer.apply_asset_event(
            event_at=event_at,
            site_name=site,
            asset=dataset,
            asset_type=AssetTypeEnum.DATASET,
        )
        seeded_datasets += 1
        print(
            f"Seeded {AssetTypeEnum.DATASET.index_name} id={doc_id(site, dataset_uuid)}"
        )
        if args.notify_peers:
            notify_queue.append((event_at, dataset, AssetTypeEnum.DATASET))

        for cap_index in range(args.captures_per_dataset):
            capture_uuid = _capture_uuid_for_index(args, site, ds_index, cap_index)
            event_at = next_event_at()
            iso = event_at.isoformat()
            center_hz = _seed_capture_center_frequency_hz(ds_index, cap_index)
            capture = sample_federated_capture_doc(
                uuid=capture_uuid,
                site_name=site,
                dataset_uuid=dataset_uuid,
                capture_props=sample_federated_drf_capture_props(
                    center_frequency_hz=center_hz,
                ),
                search_props=sample_federated_capture_search_props(
                    center_frequency_hz=center_hz,
                ),
            )
            capture = capture.model_copy(
                update={
                    "name": f"{prefix} capture {ds_index}-{cap_index}",
                    "channel": f"ch{cap_index}",
                    "public_dataset_ids": [str(dataset_uuid)],
                    "created_at": iso,
                    "updated_at": iso,
                },
            )
            indexer.apply_asset_event(
                event_at=event_at,
                site_name=site,
                asset=capture,
                asset_type=AssetTypeEnum.CAPTURE,
            )
            seeded_captures += 1
            print(
                f"Seeded {AssetTypeEnum.CAPTURE.index_name} "
                f"id={doc_id(site, capture_uuid)}"
            )
            if args.notify_peers:
                notify_queue.append((event_at, capture, AssetTypeEnum.CAPTURE))

    print(
        f"Done: {seeded_datasets} dataset(s), {seeded_captures} capture(s); "
        f"site_name={site!r}  opensearch={args.opensearch_url}"
    )
    if args.notify_peers:
        if notify_queue:
            asyncio.run(_notify_peers_for_assets(site, notify_queue))
        else:
            print("No assets seeded; skipped peer webhook notification")
    else:
        print(
            "Restart the *other* site's sync (or wait for site-hello) "
            "to pull these docs, or re-run with --notify-peers."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
