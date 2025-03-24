"""API functions specific to captures."""

from __future__ import annotations

import json
import random
import uuid
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Any
from uuid import uuid4

import pydantic
from loguru import logger as log

from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureOrigin
from spectrumx.models.captures import CaptureType
from spectrumx.utils import log_user_warning

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
        top_level_dir: Path | PurePosixPath,
        capture_type: CaptureType,
        index_name: str = "",
        channel: str | None = None,
        scan_group: str | None = None,
    ) -> Capture:
        """Creates a new RF capture in SDS.

        An SDS capture is a collection of RF files that follow a predetermined structure
        which makes them suitable for indexing and searching. Example capture types
        include Digital-RF and RadioHound. The exact file structure and what files
        get indexed depend on the capture type.

        ### Notes:

        + This method doesn't upload files, it is a lightweight method that only groups
        files already in SDS into a capture. To upload files, see `upload()` and
        `upload_file()` from your SDS client instance.

        + The `top_level_dir` is the path in SDS relative to your user directory
        where the files were uploaded to, not your local filesystem path.

        Args:
            top_level_dir:  Virtual directory in SDS where capture files are stored.
            capture_type:   One of `spectrumx.models.captures.CaptureType`.
            index_name:     The SDS index name. Leave empty to automatically select.
            channel:        (For Digital-RF) the DRF channel name to index.
            scan_group:     (For RadioHound) UUIDv4 that groups RH files.
        Returns:
            The created capture object.
        """
        if index_name:
            log.warning(
                "The 'index_name' parameter is deprecated and "
                "will be removed in future versions."
            )
        index_name = index_mapping.get(capture_type, index_name)
        if not index_name:
            log.warning(f"Could not find an index for {capture_type=}")

        top_level_dir = PurePosixPath(top_level_dir)
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
                files=[],
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

    def listing(self, *, capture_type: CaptureType | None = None) -> list[Capture]:
        """Lists all RF captures in SDS under the current user.

        Note a capture must be manually "`.create()`-d" before it can be listed, even
            if all the files are uploaded to SDS.

        Args:
            capture_type:   The type of capture to list. If empty, it lists everything.
        Returns:
            A list of the RF captures found owned by the requesting user.
        """
        log.debug(f"Listing captures of type {capture_type}")
        if self.dry_run:
            log.debug("Dry run enabled: simulating capture listing")
            num_captures: int = 3
            rng = random.Random()  # noqa: S311
            return [
                _generate_capture(
                    capture_type=capture_type
                    if capture_type
                    else rng.choice(list(CaptureType))
                )
                for _ in range(num_captures)
            ]
        captures_raw = self.gateway.list_captures(capture_type=capture_type)
        captures_list_raw, has_more = _extract_page_from_payload(captures_raw)
        if has_more:
            log.warning("Not all capture results may be listed. ")
            # TODO: request more pages if needed
        captures: list[Capture] = []
        for captures_raw in captures_list_raw:
            try:
                capture = Capture.model_validate(captures_raw)
                captures.append(capture)
            except pydantic.ValidationError as err:
                log_user_warning(f"Validation error loading capture: {captures_raw}")
                log.exception(err)
                continue
        log.debug(f"Listing {len(captures)} captures")
        return captures

    def update(
        self,
        *,
        capture_uuid: uuid.UUID,
    ) -> None:
        """Updates a capture in SDS by re-discovering and re-indexing the files.

        Note that, just like the `.create()`, this method doesn't upload files.

        Args:
            capture_uuid:   The UUID of the capture to update.
        Returns:
            None
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
        """Reads a specific capture from SDS.

        This differs from the `.listing()` method by retrieving more information about
            the capture, including the associated files' UUID, directory, and name;
            useful when working with a specific capture.

        Args:
            capture_uuid:   The UUID of the capture to read.
        Returns:
            The capture object.
        """
        log.debug(f"Reading capture with UUID {capture_uuid}")

        capture_raw = self.gateway.read_capture(capture_uuid=capture_uuid)
        capture = Capture.model_validate_json(capture_raw)
        log.debug(f"Capture read with UUID {capture.uuid}")
        return capture


def _extract_page_from_payload(
    capture_result_raw: bytes,
) -> tuple[list[dict[str, Any]], bool | None]:
    """Extracts the page from the payload.
    Args:
        capture_result_raw: The raw capture result from the API.
    Returns:
        The list of captures;
        A boolean indicating if there are more pages, or None if it can't be determined.
    """
    captures_object = json.loads(capture_result_raw)
    ret_captures_list: list[dict[str, Any]] = captures_object.get(
        "results", captures_object
    )

    # check if we need to request more pages
    has_more: bool | None
    if "next" not in ret_captures_list:
        has_more = None
    else:
        next_url: str = captures_object["next"]
        has_more = bool(next_url)

    # if result looks like a single capture, make sure it's a list
    if isinstance(ret_captures_list, dict):
        ret_captures_list = [ret_captures_list]

    return ret_captures_list, has_more


def _generate_capture(capture_type: CaptureType) -> Capture:
    """Generates a fake capture for testing purposes."""
    return Capture(
        capture_props={"_comment": "Simulated capture for a dry-run"},
        capture_type=capture_type,
        index_name="",
        channel=None,
        scan_group=None,
        origin=CaptureOrigin.User,
        top_level_dir=PurePosixPath("/"),
        uuid=uuid4(),
        files=[],
    )
