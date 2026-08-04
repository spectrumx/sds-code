#!/usr/bin/env python3
"""Seed dummy federated docs into a peer OpenSearch (no gateway).

Use for peer→main backfill / list-* tests. ``site_name`` must be the peer FQDN
(matches federation.toml ``[site].fqdn``).

Examples::

  # Local peer stack (OpenSearch on host :9201)
  uv run python scripts/seed_peer_opensearch.py \\
    --opensearch-url http://localhost:9201 \\
    --site-name peer.local

  # Remote peer after port-forward / public OS URL
  uv run python scripts/seed_peer_opensearch.py \\
    --opensearch-url https://peer-os.example:9200 \\
    --site-name peer.example.com \\
    --user admin --password secret
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC
from datetime import datetime
from uuid import UUID

from opensearchpy import OpenSearch
from sds_federation.schemas.webhooks import AssetTypeEnum
from sds_federation.services.fed_index import FederatedAssetIndexer
from sds_federation.services.fed_index import doc_id
from sds_federation.services.fed_index import ensure_fed_indices
from sds_federation.testing.sample_data import TEST_CAPTURE_UUID
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import sample_federated_capture_doc
from sds_federation.testing.sample_data import sample_federated_dataset_doc


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
    p.add_argument("--dataset-uuid", default=str(TEST_DATASET_UUID))
    p.add_argument("--capture-uuid", default=str(TEST_CAPTURE_UUID))
    p.add_argument("--user", default="", help="Optional basic-auth user")
    p.add_argument("--password", default="", help="Optional basic-auth password")
    p.add_argument(
        "--use-ssl",
        action="store_true",
        help="Force SSL client (also inferred from https:// URL)",
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


def main() -> int:
    args = _parse_args()
    site = args.site_name.strip()
    if not site:
        print("ERROR: --site-name is required", file=sys.stderr)
        return 1

    dataset_uuid = UUID(args.dataset_uuid)
    capture_uuid = UUID(args.capture_uuid)
    client = _client_from_url(args)
    ensure_fed_indices(client)
    indexer = FederatedAssetIndexer(client)
    event_at = datetime.now(UTC)

    dataset = sample_federated_dataset_doc(uuid=dataset_uuid, site_name=site)
    dataset = dataset.model_copy(
        update={
            "name": f"Peer seed dataset ({site})",
            "is_public": True,
            "status": "final",
            "status_display": "Final",
            "created_at": event_at.isoformat(),
            "updated_at": event_at.isoformat(),
        },
    )
    capture = sample_federated_capture_doc(uuid=capture_uuid, site_name=site)
    capture = capture.model_copy(
        update={
            "name": f"Peer seed capture ({site})",
            "channel": "chA",
            "public_dataset_ids": [str(dataset_uuid)],
            "created_at": event_at.isoformat(),
            "updated_at": event_at.isoformat(),
        },
    )

    indexer.apply_asset_event(
        event_at=event_at,
        site_name=site,
        asset=dataset,
        asset_type=AssetTypeEnum.DATASET,
    )
    indexer.apply_asset_event(
        event_at=event_at,
        site_name=site,
        asset=capture,
        asset_type=AssetTypeEnum.CAPTURE,
    )

    print(f"Seeded {AssetTypeEnum.DATASET.index_name} id={doc_id(site, dataset_uuid)}")
    print(f"Seeded {AssetTypeEnum.CAPTURE.index_name} id={doc_id(site, capture_uuid)}")
    print(f"site_name={site!r}  opensearch={args.opensearch_url}")
    print(
        "Restart the *other* site's sync (or wait for site-hello) to pull these docs."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
