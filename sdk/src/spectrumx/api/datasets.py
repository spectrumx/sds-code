"""API functions specific to datasets."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid

from spectrumx.models.files import File
from spectrumx.ops.pagination import Paginator
from spectrumx.utils import log_user

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

    def get_files(
        self,
        dataset_uuid: uuid.UUID,
    ) -> Paginator[File]:
        """Get files in the dataset as a paginator.

        Args:
            dataset_uuid: The UUID of the dataset to get files for.
        Returns:
            A paginator for the files in the dataset.
        """
        if self.dry_run:
            log_user("Dry run enabled: files will be simulated")

        # Create a paginator that fetches from the dataset files endpoint
        pagination: Paginator[File] = Paginator(
            Entry=File,
            gateway=self.gateway,
            list_method=self.gateway.get_dataset_files,
            list_kwargs={"dataset_uuid": dataset_uuid},
            dry_run=self.dry_run,
            verbose=self.verbose,
        )

        return pagination
