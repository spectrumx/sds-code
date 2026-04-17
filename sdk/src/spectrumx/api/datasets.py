"""API functions specific to datasets."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger as log

from spectrumx.models.files import File
from spectrumx.ops.pagination import Paginator
from spectrumx.utils import log_user

if TYPE_CHECKING:
    from uuid import UUID

    from spectrumx.gateway import GatewayClient


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
        dataset_uuid: UUID,
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

    def delete(
        self,
        dataset_uuid: UUID,
        *,
        bypass_share_guard: bool = False,
    ) -> bool:
        """Deletes a dataset from SDS by its UUID.

        Args:
            dataset_uuid: The UUID of the dataset to delete.
            bypass_share_guard: If True, request unshare then delete when the dataset
                is shared (gateway ``bypass_share_guard`` query param).
        Returns:
            True if the dataset was deleted successfully, or if in dry run mode.
        """
        if self.verbose:
            log.debug(f"Deleting dataset with UUID {dataset_uuid}")

        if self.dry_run:
            log.debug(f"Dry run enabled: would delete dataset {dataset_uuid}")
            return True

        self.gateway.delete_dataset(
            dataset_uuid=dataset_uuid,
            bypass_share_guard=bypass_share_guard,
        )
        if self.verbose:
            log.debug(f"Dataset deleted with UUID {dataset_uuid}")
        return True

    def revoke_share_permissions(self, dataset_uuid: UUID) -> bool:
        """Revoke all direct share permissions on this dataset (owner-only).

        Use this (or the web portal) before :meth:`delete` when the dataset is shared.
        """
        if self.verbose:
            log.debug(f"Revoking share permissions for dataset {dataset_uuid}")
        if self.dry_run:
            log.debug("Dry run enabled: would revoke dataset share permissions")
            return True
        self.gateway.revoke_dataset_share_permissions(dataset_uuid=dataset_uuid)
        return True

    def delete_after_revoking_share(self, dataset_uuid: UUID) -> bool:
        """Revoke direct shares, then delete the dataset."""
        self.revoke_share_permissions(dataset_uuid)
        return self.delete(dataset_uuid)
