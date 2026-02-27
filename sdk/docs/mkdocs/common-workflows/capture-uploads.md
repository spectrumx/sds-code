# SDS Capture Uploads (Digital-RF)

+ [SDS Capture Uploads (Digital-RF)](#sds-capture-uploads-digital-rf)
    + [Checklist](#checklist)
    + [Context](#context)
    + [Script](#script)

The script below walks through uploading a local Digital-RF directory to SDS and
creating one or more captures from the uploaded files. If the capture creation step
fails (e.g. the capture already exists, or metadata couldn't be extracted by SDS for
indexing), the script reassures the user that the data is safe in SDS and advises on
next steps.

## Checklist

+ [ ] Have a Python environment with `spectrumx` and `loguru` installed.
    + Recommended: `uv init` + `uv add spectrumx loguru` to create an isolated
      environment with the required dependencies.
+ [ ] Make sure the local Digital-RF directory exists and follows the standard
    directory layout (top-level directory containing channel subdirectories, each
     with `rf_data` and `metadata` folders).
+ [ ] Set up your SDS API key in a `.env` file in the same directory as the script
    below.
        + Generate a key at <https://sds.crc.nd.edu/users/generate-api-key-form/>
        + Create a `.env` file with the line `SDS_SECRET_TOKEN=your_api_key_here`
+ [ ] Update the `drf_local_path` variable below to point to your Digital-RF directory.
+ [ ] Update `sds_destination` to the virtual path in SDS where the files should live.
+ [ ] By default, channels are auto-discovered by this script from subdirectories
    containing `drf_properties.h5`. To override, set `drf_channel` (single) or
    `drf_channels` (multi) manually in the script.
+ [ ] Follow any other "`TODO`" comments in the script.

## Context

A Digital-RF capture in SDS is created from files that are already uploaded. The
workflow is therefore two steps:

1. **Upload** the local Digital-RF directory to SDS via `client.upload()`.
2. **Create the capture** via `client.captures.create()`, pointing it at the
    virtual path where the files now live.

Because the upload is independent of the capture, a failure during step 2 does
**not** mean data was lost — the files remain safely stored in SDS and the capture
can be retried later.

The script below handles both single-channel and multi-channel Digital-RF
captures and includes retry logic with exponential backoff for transient network
or service errors.

/// tip | Using an unreliable connection?

If you are using an unreliable connection, consider turning `persist_state`
below to `True`

///

## Script

```python
#!/usr/bin/env python
"""Upload a Digital-RF capture to SDS with error handling.

Channel auto-discovery:
    By default, the script scans `drf_local_path` for subdirectories containing
    a `drf_properties.h5` file and treats each as a channel.

Manual override:
    Set `drf_channel` to a single channel name, or `drf_channels` to an explicit
    list, to skip auto-discovery.

For documentation, see https://sds.crc.nd.edu/sdk/
"""

import sys
import time
from pathlib import Path, PurePosixPath
from uuid import UUID

from loguru import logger as log

from spectrumx import Client
from spectrumx.errors import CaptureError, NetworkError, Result, SDSError, ServiceError
from spectrumx.models.captures import Capture, CaptureType
from spectrumx.models.files import File

DRF_PROPERTIES_FILENAME = "drf_properties.h5"


def discover_drf_channels(drf_root: Path) -> list[str]:
    """Scan a Digital-RF directory for channels.

    A subdirectory is considered a channel if it contains a `drf_properties.h5` file.

    Args:
        drf_root: Top-level Digital-RF directory.

    Returns:
        Sorted list of discovered channel names.
    """
    channels = sorted(
        subdir.name
        for subdir in drf_root.iterdir()
        if subdir.is_dir() and (subdir / DRF_PROPERTIES_FILENAME).is_file()
    )
    return channels


def upload_with_retries(
    *,
    client: Client,
    local_path: Path,
    sds_path: PurePosixPath,
    retries: int = 5,
) -> list[File]:
    """Upload a local directory to SDS, retrying on transient failures.

    Args:
        client:     Authenticated SDS client.
        local_path: Local directory containing Digital-RF data.
        sds_path:   Virtual destination path in SDS.
        retries:    Maximum number of retry attempts.

    Returns:
        The list of successfully uploaded File objects.

    Raises:
        SDSError: When all retries are exhausted or a non-retryable error occurs.
    """
    sleep_sec = 1
    max_sleep_sec = 300

    for attempt in range(1, retries + 1):
        try:
            results: list[Result[File]] = client.upload(
                local_path=local_path,
                sds_path=sds_path,
                verbose=True,
                persist_state=False,
                # setting persist_state to True speeds up retries, but it also won't
                # re-upload files the local machine considers to be uploaded (which
                # could differ from the server state).
            )
        except (NetworkError, ServiceError) as err:
            if attempt == retries:
                raise
            sleep_sec = min(sleep_sec * 2, max_sleep_sec)
            log.warning(
                f"Upload attempt {attempt} failed: {err}; retrying in {sleep_sec}s"
            )
            time.sleep(sleep_sec)
            continue

        succeeded = [r for r in results if r]
        failed = [r for r in results if not r]

        if not failed:
            if client.dry_run:
                log.warning(
                    f"Would have uploaded {len(succeeded)} files successfully (disable dry-run mode to upload)."
                )
            else:
                log.success(f"All {len(succeeded)} files uploaded successfully.")
            return [r.unwrap() for r in succeeded]

        log.warning(f"{len(failed)} of {len(succeeded) + len(failed)} uploads failed.")
        for r in failed:
            log.error(f"  {r.exception_or(SDSError('unknown'))}")

        if attempt < retries:
            sleep_sec = min(sleep_sec * 2, max_sleep_sec)
            log.info(f"Retrying in {sleep_sec}s (attempt {attempt + 1}/{retries})...")
            time.sleep(sleep_sec)
        else:
            msg = (
                f"{len(failed)} file(s) could not be uploaded after {retries} attempts."
            )
            raise SDSError(msg)

    msg = "Upload loop exited unexpectedly."
    raise SDSError(msg)


def create_single_channel_capture(
    *,
    client: Client,
    sds_path: PurePosixPath,
    channel: str,
    name: str | None = None,
) -> Capture | None:
    """Create a single-channel Digital-RF capture.

    Args:
        client:   Authenticated SDS client.
        sds_path: Virtual path in SDS where files were uploaded.
        channel:  Digital-RF channel name.
        name:     Optional human-readable name for the capture.

    Returns:
        The created Capture, or None if creation failed.
    """
    try:
        capture = client.captures.create(
            top_level_dir=sds_path,
            capture_type=CaptureType.DigitalRF,
            channel=channel,
            name=name,
        )
    except CaptureError as err:
        _report_capture_failure(err)
        return None
    else:
        if client.dry_run:
            log.warning(
                f"Would have created capture for channel '{channel}' successfully (disable dry-run mode to create)."
            )
        else:
            log.success(f"Capture created: {capture.uuid}")
        return capture


def create_multichannel_captures(
    *,
    client: Client,
    sds_path: PurePosixPath,
    channels: list[str],
) -> list[Capture]:
    """Create a Digital-RF capture for each channel.

    Args:
        client:   Authenticated SDS client.
        sds_path: Virtual path in SDS where files were uploaded.
        channels: List of Digital-RF channel names.

    Returns:
        List of successfully created Capture objects (may be shorter than channels).
    """
    captures: list[Capture] = []
    for ch in channels:
        try:
            capture = client.captures.create(
                top_level_dir=sds_path,
                capture_type=CaptureType.DigitalRF,
                channel=ch,
            )
        except CaptureError as err:
            existing_uuid_str = err.extract_existing_capture_uuid()
            if existing_uuid_str:
                log.info(
                    f"Capture for channel '{ch}' already exists: {existing_uuid_str}"
                )
                captures.append(
                    client.captures.read(capture_uuid=UUID(existing_uuid_str))
                )
            else:
                _report_capture_failure(err, channel=ch)
        else:
            log.success(f"Capture for channel '{ch}' created: {capture.uuid}")
            captures.append(capture)

    return captures


def _report_capture_failure(err: CaptureError, *, channel: str | None = None) -> None:
    """Log a reassuring message when capture creation fails.

    Args:
        err:     The CaptureError that was raised.
        channel: Optional channel name for context.
    """
    target = f" for channel '{channel}'" if channel else ""
    log.error(f"Capture creation{target} failed: {err}")
    log.info(
        "Your files were uploaded successfully and are safely stored in SDS. "
        "The capture could not be created at this time. Possible reasons:\n"
        "  + The capture may already exist (duplicate channel + directory).\n"
        "  + The uploaded files may not yet match the expected Digital-RF structure.\n"
        "  + A transient server-side indexing delay.\n"
        "You can retry capture creation later with client.captures.create() "
        "or via the SDS web interface."
    )


def main() -> None:
    # ── client setup ──────────────────────────────────────────────
    client = Client(
        host="sds.crc.nd.edu",
        # TODO: create a .env file with your SDS API token for authentication
        # env_file=Path(".env"),  # default
    )
    client.dry_run = False  # ⚠️ required to actually upload files
    client.authenticate()

    # ── paths ─────────────────────────────────────────────────────
    # TODO: set these to match your local Digital-RF directory and
    #       chosen SDS destination
    drf_local_path = Path("./rf_data")
    sds_destination = PurePosixPath(f"drf_capture_{int(time.time())}")

    if not drf_local_path.is_dir():
        log.error(f"Directory not found: {drf_local_path}")
        log.info(
            "Please update drf_local_path to point to your Digital-RF directory and try again."
        )
        sys.exit(1)

    # ── channel discovery ─────────────────────────────────────────
    # Auto-discover channels from subdirs that contain drf_properties.h5.
    # To override, set drf_channel (single) or drf_channels (multi) manually.
    drf_channel: str | None = None
    drf_channels: list[str] = discover_drf_channels(drf_local_path)
    log.info(f"Discovered {len(drf_channels)} channel(s): {drf_channels}")

    # ── step 1: upload ────────────────────────────────────────────
    log.info(f"Uploading '{drf_local_path}' → SDS:/{sds_destination}")
    uploaded_files = upload_with_retries(
        client=client,
        local_path=drf_local_path,
        sds_path=sds_destination,
    )
    log.info(f"{len(uploaded_files)} file(s) now stored in SDS.")

    # ── step 2: create capture(s) ─────────────────────────────────
    if len(drf_channels) > 1:
        captures = create_multichannel_captures(
            client=client,
            sds_path=sds_destination,
            channels=drf_channels,
        )
        log.info(f"Created {len(captures)} of {len(drf_channels)} channel captures.")
    elif len(drf_channels) == 1 or drf_channel:
        channel = drf_channels[0] if drf_channels else drf_channel
        assert channel is not None
        capture = create_single_channel_capture(
            client=client,
            sds_path=sds_destination,
            channel=channel,
            name="My Digital-RF Capture",
        )
        if capture:
            log.info(f"Capture UUID: {capture.uuid}")
            log.info("Capture details:")
            log.info(f"  Channel: {capture.channel}")
            log.info(f"  Created at: {capture.created_at}")
            log.info(f"  Number of files: {len(capture.files)}")
            log.info(f"  Path in SDS: {capture.top_level_dir}")
            if not client.dry_run:
                log.info(
                    f"  Capture page: https://sds.crc.nd.edu/api/v1/assets/captures/{capture.uuid}/"
                )
    else:
        log.warning(
            "No channels discovered or specified — files were uploaded but no "
            "capture was created. Verify your Digital-RF directory contains "
            f"subdirectories with '{DRF_PROPERTIES_FILENAME}' files, or set "
            "drf_channel / drf_channels manually."
        )


if __name__ == "__main__":
    main()
```
