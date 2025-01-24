"""API functions specific to captures."""

from __future__ import annotations

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
        log.debug("Capture created: {}", capture)
        return capture
