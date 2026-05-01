"""API functions specific to datasets."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from typing import Any

from loguru import logger as log

from spectrumx.models.datasets import Dataset
from spectrumx.models.files import File
from spectrumx.ops.pagination import Paginator
from spectrumx.utils import log_user

if TYPE_CHECKING:
    from collections.abc import Collection
    from pathlib import Path
    from pathlib import PurePosixPath
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

    def get(self, dataset_uuid: UUID) -> Dataset:
        """Load dataset metadata, captures, and artifact files from SDS.

        Captures are returned in the same grouped shape as the capture list API
        (one entry per logical multi-channel capture where applicable). For every
        file in the dataset (including capture-linked files), use :meth:`get_files`
        instead, which calls the paginated dataset files manifest endpoint.
        """
        if self.dry_run:
            log_user("Dry run enabled: returning an empty Dataset shell")
            return Dataset(uuid=dataset_uuid)

        raw = self.gateway.get_dataset(
            dataset_uuid=dataset_uuid,
            verbose=self.verbose,
        )
        return Dataset.model_validate_json(raw)

    def list_captures(self, dataset_uuid: UUID) -> list[dict[str, Any]]:
        """Return capture payloads linked to the dataset (raw JSON objects).

        Use this when you need composite capture fields (for example ``channels``)
        without coercing through :class:`~spectrumx.models.datasets.DatasetCapture`.
        """
        if self.dry_run:
            log_user("Dry run enabled: returning an empty capture list")
            return []

        raw = self.gateway.get_dataset(
            dataset_uuid=dataset_uuid,
            verbose=self.verbose,
        )
        data = json.loads(raw)
        captures = data.get("captures")
        return list(captures) if isinstance(captures, list) else []

    def list_artifact_files(self, dataset_uuid: UUID) -> list[dict[str, Any]]:
        """Return file rows linked directly to the dataset (artifacts), as JSON dicts.

        These are the same objects embedded on :meth:`get` under the ``files`` key.
        For the full downloadable manifest (captures plus artifacts), use
        :meth:`get_files`.
        """
        if self.dry_run:
            log_user("Dry run enabled: returning an empty artifact file list")
            return []

        raw = self.gateway.get_dataset(
            dataset_uuid=dataset_uuid,
            verbose=self.verbose,
        )
        data = json.loads(raw)
        files = data.get("files")
        return list(files) if isinstance(files, list) else []

    def get_files(
        self,
        dataset_uuid: UUID,
        *,
        capture_uuids: Collection[UUID] | None = None,
        top_level_dirs: Collection[PurePosixPath | Path | str] | None = None,
        artifacts_only: bool = False,
    ) -> Paginator[File]:
        """Get files in the dataset as a paginator.

        Args:
            dataset_uuid: The UUID of the dataset to get files for.
            capture_uuids: If set, passed to the gateway to restrict by capture UUID (OR
                with ``top_level_dirs``).
            top_level_dirs: If set, passed to the gateway as path prefixes under
                ``File.directory`` (OR with ``capture_uuids``).
            artifacts_only: If set, only return artifact files (not capture-linked
                files).
        Returns:
            A paginator for the files in the dataset.
        """
        if self.dry_run:
            log_user("Dry run enabled: files will be simulated")

        if artifacts_only and capture_uuids:
            log.warning("Capture UUIDs are not allowed when artifacts_only is True.")
            capture_uuids = None

        if artifacts_only and top_level_dirs:
            log.info("Top level directories included will ONLY return artifact files.")

        list_kwargs: dict[str, Any] = {"dataset_uuid": dataset_uuid}
        if capture_uuids is not None:
            list_kwargs["capture_uuids"] = tuple(capture_uuids)
        if top_level_dirs is not None:
            list_kwargs["top_level_dirs"] = tuple(str(p) for p in top_level_dirs)
        if artifacts_only:
            list_kwargs["artifacts_only"] = True

        pagination: Paginator[File] = Paginator(
            Entry=File,
            gateway=self.gateway,
            list_method=self.gateway.get_dataset_files,
            list_kwargs=list_kwargs,
            dry_run=self.dry_run,
            verbose=self.verbose,
        )

        return pagination

    def delete(
        self,
        dataset_uuid: UUID,
    ) -> bool:
        """Deletes a dataset from SDS by its UUID.

        Args:
            dataset_uuid: The UUID of the dataset to delete.
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
