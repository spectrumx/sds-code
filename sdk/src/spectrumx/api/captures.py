"""API functions specific to captures."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING
from uuid import uuid4

from loguru import logger as log

from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.captures import CaptureType

if TYPE_CHECKING:
    from pathlib import Path

    from spectrumx.gateway import GatewayClient

index_mapping = {
    CaptureType.DigitalRF: "captures-drf",
    CaptureType.RadioHound: "captures-rh",
}


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
        capture_type: CaptureType,
        index_name: str = "",
        channel: str | None = None,
        scan_group: str | None = None,
    ) -> Capture:
        """Creates a new capture in SDS."""
        if index_name:
            log.warning(
                "The 'index_name' parameter is deprecated and "
                "will be removed in future versions."
            )
        index_name = index_mapping.get(capture_type, index_name)
        if not index_name:
            log.warning(f"Could not find an index for {capture_type=}")
        log.debug(
            f"Creating capture with {top_level_dir=}, "
            f"{channel=}, {capture_type=}, {index_name=}, {scan_group=}"
        )

        if self.dry_run:
            log.debug("Dry run enabled: simulating the capture creation")
            return Capture(
                capture_props={},
                capture_type=capture_type,
                channel=channel,
                index_name=index_name,
                origin=CaptureOrigin.User,
                scan_group=uuid.UUID(scan_group) if scan_group else None,
                top_level_dir=top_level_dir,
                uuid=uuid4(),
            )
        capture_raw = self.gateway.create_capture(
            capture_type=capture_type,
            channel=channel,
            index_name=index_name,
            scan_group=scan_group,
            top_level_dir=top_level_dir,
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

    def update(
        self,
        *,
        capture_uuid: uuid.UUID,
    ) -> None:
        """Updates a capture in SDS by re-discovering and re-indexing the files.

        Re-upload the desired capture files in order to change
        """
        log.debug(f"Updating capture with UUID {capture_uuid}")

        if self.dry_run:
            log.debug(f"Dry run enabled: simulating capture update {capture_uuid}")
            return

        capture_raw = self.gateway.update_capture(
            capture_uuid=capture_uuid,
            verbose=True,
        )
        capture = Capture.model_validate_json(capture_raw)
        log.debug(f"Capture updated with UUID {capture.uuid}")

    def read(
        self,
        *,
        capture_uuid: uuid.UUID,
    ) -> Capture:
        """Reads a specific capture from SDS."""
        log.debug(f"Reading capture with UUID {capture_uuid}")

        capture_raw = self.gateway.read_capture(capture_uuid=capture_uuid)
        capture = Capture.model_validate_json(capture_raw)
        log.debug(f"Capture read with UUID {capture.uuid}")
        return capture
