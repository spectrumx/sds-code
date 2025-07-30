"""API functions specific to datasets."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from loguru import logger as log

from spectrumx.errors import DatasetError
from spectrumx.utils import log_user_warning

if TYPE_CHECKING:
    from spectrumx.gateway import GatewayClient

# python 3.10 backport
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone

    UTC = timezone.utc  # noqa: UP017


class DatasetAPI:
    gateway: GatewayClient
    verbose: bool = False

    def __init__(
        self,
        *,
        gateway: GatewayClient,
        dry_run: bool = True,
        verbose: bool = False,
    ) -> None:
        """Initializes the DatasetAPI."""
        self.dry_run = dry_run
        self.gateway = gateway
        self.verbose = verbose

    def download(
        self,
        dataset_uuid: uuid.UUID,
        to_local_path: Path | str,
    ) -> Path:
        """Downloads a dataset as a ZIP file from SDS.

        Args:
            dataset_uuid: The UUID of the dataset to download.
            to_local_path: The local path to save the downloaded ZIP file to.
        Returns:
            The path to the downloaded ZIP file.
        Raises:
            DatasetError: If the dataset couldn't be downloaded.
        """
        to_local_path = Path(to_local_path)

        if self.dry_run:
            log_user_warning("Dry run: simulating dataset download")
            # Create a dummy ZIP file for dry run
            if not to_local_path.parent.exists():
                to_local_path.parent.mkdir(parents=True)
            to_local_path.write_bytes(b"# Dry run: dummy dataset ZIP content")
            return to_local_path

        try:
            # Ensure the directory exists
            to_local_path.parent.mkdir(parents=True, exist_ok=True)

            # Download the dataset ZIP
            response = self.gateway.download_dataset(dataset_uuid=dataset_uuid)

            # Write the ZIP file to disk
            with open(to_local_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            log.info(f"Successfully downloaded dataset to {to_local_path}")
            return to_local_path

        except OSError as e:
            msg = f"File system error downloading dataset {dataset_uuid}: {e}"
            log.error(msg)
            raise DatasetError(msg) from e
        except requests.RequestException as e:
            msg = f"Network error downloading dataset {dataset_uuid}: {e}"
            log.error(msg)
            raise DatasetError(msg) from e
