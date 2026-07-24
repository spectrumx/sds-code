#!/usr/bin/env python3
"""Publish a simulated federation:events message to Redis (manual integration).

Automated tests use pytest with dispatch_federation_redis_payload and no Redis.

Usage:
  REDIS_URL=redis://localhost:6379/0 uv run python scripts/simulate_redis_event.py
  REDIS_URL=... uv run python scripts/simulate_redis_event.py --uuid aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from uuid import UUID

import redis
from sds_federation.models import load_federation_config
from sds_federation.services.redis_channel import resolve_federation_events_channel
from sds_federation.testing.sample_data import TEST_DATASET_UUID
from sds_federation.testing.sample_data import simulated_dataset_redis_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Publish simulated federation Redis event"
    )
    parser.add_argument(
        "--uuid",
        default=str(TEST_DATASET_UUID),
        help="Dataset UUID in the event payload",
    )
    args = parser.parse_args()

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    config = load_federation_config()
    channel = resolve_federation_events_channel(
        site_name=config.site.name,
        env_override=os.environ.get("FEDERATION_EVENTS_CHANNEL"),
    )
    payload = simulated_dataset_redis_payload(
        uuid=UUID(args.uuid),
    )
    client = redis.from_url(redis_url)
    receivers = client.publish(channel, json.dumps(payload))
    print(f"Published to {channel!r} on {redis_url} ({receivers} subscribers)")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
