"""API functions specific to captures."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger as log

from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.captures import CaptureType

if TYPE_CHECKING:
    from pathlib import Path

    from spectrumx.gateway import GatewayClient


class CaptureAPI:
    client: GatewayClient

    def __init__(self, *, gateway: GatewayClient, dry_run: bool = True) -> None:
        """Initializes the CaptureAPI."""
        self.dry_run = dry_run
        self.gateway = gateway

    def create(
        self,
        *,
        top_level_dir: Path,
        channel: str,
        capture_type: CaptureType,
        index_name: str,
    ) -> Capture:
        """Creates a new capture in SDS."""
        log.debug(
            f"Creating capture with {top_level_dir=}, "
            f"{channel=}, {capture_type=}, {index_name=}"
        )

        if self.dry_run:
            log.debug("Dry run enabled: simulating the capture creation")
            return Capture(
                capture_props={},
                capture_type=capture_type,
                channel=channel,
                index_name=index_name,
                origin=CaptureOrigin.User,
                top_level_dir=top_level_dir,
                uuid=uuid4(),
            )
        capture_raw = self.gateway.create_capture(
            top_level_dir=top_level_dir,
            channel=channel,
            capture_type=capture_type,
            index_name=index_name,
        )
        capture = Capture.model_validate_json(capture_raw)
        log.debug(f"Capture created with UUID {capture.uuid}")
        return capture

    def listing(self, *, capture_type: CaptureType) -> list[Capture]:
        """Lists all captures in SDS under the current user."""
        log.debug(f"Listing captures of type {capture_type}")
        captures_raw = self.gateway.list_captures(capture_type=capture_type)
        captures_list_raw = json.loads(captures_raw)
        captures: list[Capture] = []
        for captures_raw in captures_list_raw:
            capture = Capture.model_validate(captures_raw)
            captures.append(capture)
        log.debug(f"Listing {len(captures)} captures")
        return captures
