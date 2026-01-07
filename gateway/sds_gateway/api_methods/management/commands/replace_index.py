"""Django management command to initialize OpenSearch indices."""

from datetime import UTC
from datetime import datetime
from typing import Any
from typing import NoReturn
from typing import cast

from django.core.management.base import BaseCommand
from django.core.management.base import CommandParser
from django.db.models import Count
from django.db.models import QuerySet
from loguru import logger as log
from opensearchpy import AuthenticationException
from opensearchpy import ConnectionError as OpensearchConnectionError
from opensearchpy import NotFoundError
from opensearchpy import OpenSearch
from opensearchpy import RequestError

from sds_gateway.api_methods.helpers.transforms import Transforms
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.utils.relationship_utils import get_capture_files
from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet

# maximum size (doc count) of OpenSearch searches
MAX_OS_SIZE = 10_000


class Command(BaseCommand):
    """
    Replace an OpenSearch index with a new mapping when updating
    the mapping schema is not possible.

    This command will:
    - find and delete duplicate captures in the database and the index
    - create a backup of the existing index
    - delete the existing index
    - create a new index with the new mapping
    - reindex the captures in the new index (skipping deleted captures)
    - apply field transforms as necessary to the new index
    - refresh the new index
    - verify the reindex was successful
    - prompt the user to reset the index to its original form
    if the reindex was not successful
    - OR if any errors occur, the command will rollback the index to its original form
    - The backup index will be kept for reference, this command will not delete it

    This command is useful when the mapping schema is updated
    and the existing index cannot be updated.

    !!WARNING!!
    Use this command with caution, it will DELETE the existing index
    and create a new one with an incompatible mapping.
    It will also hard DELETE (duplicate) captures from the index and database.
    ONLY use if init_indices fails to update the index.

    **Make sure to back up the existing OpenSearch and PostgreSQL databases
    before running this command.**

    While this command includes a backup and restore process and defensive measures,
    it is still possible to lose data, so use at your own risk!
    """

    help = """
    Replace an OpenSearch index with a new one
    when updating the mapping schema is not possible.

    !!WARNING!!
    Use this command with caution, it will DELETE the existing index
    and create a new one with an incompatible mapping.
    It will also hard DELETE (duplicate) captures from the index and database.
    ONLY use if init_indices fails to update the index.

    **Make sure to back up the existing OpenSearch and PostgreSQL databases
    before running this command.**
    """

    def add_arguments(self, parser: CommandParser) -> None:
        """Arguments for this command."""
        parser.add_argument(
            "--index_name",
            type=str,
            help="Index name to reset",
            required=True,
        )

        parser.add_argument(
            "--capture_type",
            type=str,
            help="Index capture type to reset",
            required=True,
        )

    def attempt_reindexing(self, backup_index_name: str) -> None:
        """Attempts to reindex the OpenSearch index."""

        self._recreate_index()
        self._reindex_valid_captures()
        self.client.indices.refresh(index=self.index_name)
        self._delete_captures_with_only_missing_files()

        is_reindex_successful, reasons = self._was_reindexing_successful()
        if not is_reindex_successful:
            return self._ask_confirmation_and_rollback(
                backup_index_name=backup_index_name,
                reasons=reasons,
            )
        new_count = self._get_doc_count()
        log.success(
            f"Successfully UPDATED index '{self.index_name}' with {new_count} docs",
        )
        return None

    def backup_index(self, backup_index_name: str) -> bool:
        """Create a backup of the current index.

        Args:
            backup_index_name: Name of the backup index to create.
        Returns:
            True if the backup was created and it's consistent. False otherwise.
        Raises:
            RequestError: If the index does not exist or an error occurs.
            OpensearchConnectionError: If the client cannot connect to OpenSearch.
        """
        self._clone_index(
            source_index=self.index_name,
            target_index=backup_index_name,
        )

        # verify backup index count matches original index count before continuing
        # get original document count
        original_count = self._get_doc_count()
        if original_count < 0:
            log.error(f"Skipping '{self.index_name}' due to count error")
            return False

        assert self._get_doc_count(backup_index_name) == original_count, (
            "Backup index count does not match original index count"
        )
        return True

    def delete_duplicate_captures_and_doc_refs(self) -> None:
        """Delete duplicate captures from index and database."""
        duplicate_capture_groups = self._find_duplicate_captures()

        log.warning(
            f"Found {len(duplicate_capture_groups)} duplicate capture groups: "
            f"{duplicate_capture_groups}",
        )

        # if the dictionary is empty, return
        if not duplicate_capture_groups:
            log.info("No duplicate captures found")
            return

        # delete duplicate captures
        for capture_group in duplicate_capture_groups.values():
            # if the capture group is not sorted by created_at, sort it
            assert (
                capture_group.order_by("created_at").first() == capture_group.first()
            ), "Capture group is not sorted by created_at"

            owners = capture_group.values_list("owner", flat=True)
            unique_owners = set(owners)
            assert len(unique_owners) == 1, (
                "Captures in the group do not belong to the same owner"
            )

            oldest_capture = capture_group.first()
            if oldest_capture is None:
                log.error(
                    "Capture group is empty, skipping deduplication...",
                )
                continue
            if capture_group.count() <= 1:
                log.warning(
                    "Capture group has 1 or fewer captures, skipping deduplication...",
                )
                continue
            duplicates_to_delete = capture_group.exclude(pk=oldest_capture.pk)

            match self.capture_type:
                case CaptureType.RadioHound:
                    scan_groups = capture_group.values_list("scan_group", flat=True)
                    distinct_scan_groups = set(scan_groups)
                    assert len(distinct_scan_groups) == 1, (
                        "Captures in the group do not belong to the same scan_group"
                    )
                case CaptureType.DigitalRF:
                    channels = capture_group.values_list("channel", flat=True)
                    dirs = capture_group.values_list("top_level_dir", flat=True)

                    distinct_channels = set(channels)
                    distinct_dirs = set(dirs)

                    assert len(distinct_channels) == 1, (
                        "Captures in the group do not belong to the same channel"
                    )
                    assert len(distinct_dirs) == 1, (
                        "Captures in the group do not belong to the same top_level_dir"
                    )
                case _:
                    log.error(f"Unknown capture type: {self.capture_type}")
                    return

            # delete all duplicates, keeping the oldest in each group
            for capture in duplicates_to_delete:
                self._delete_doc_by_capture_uuid(
                    capture_uuid=capture.uuid,
                )
                capture.delete()
                log.success(
                    f"Successfully DELETED duplicate capture '{capture.uuid}'",
                )
            self.client.indices.refresh(index=self.index_name)

    def delete_index(self, index_name: str) -> None:
        """Delete an index."""
        log.info(f"Deleting index '{index_name}'...")
        self.client.indices.delete(index=index_name)
        log.success(
            f"Successfully DELETED index '{index_name}'",
        )

    def get_indices_stats(self) -> dict[str, dict[str, Any]]:
        """Shows number of docs across stats indices and returns their mapping."""
        maps = self.client.indices.get_mapping(index="*")
        for index_name in maps:
            doc_count = self._get_doc_count(index_name)
            log.warning(
                f"{index_name:>60} index: {doc_count:>6} documents",
            )

        return maps

    def handle(self, *args, **options) -> None:
        """Executes the replace index command."""
        response = input(
            "WARNING: This command is potentially destructive to existing "
            "Capture and OpenSearch index data and should be used with "
            "extreme caution.\n"
            "Are you sure you want to continue? (y/N): ",
        ).lower()
        if response != "y":
            log.warning("Command cancelled.")
            return None

        # set shared variables
        self.client: OpenSearch = get_opensearch_client()
        self.capture_type = options["capture_type"]
        self.index_name = options["index_name"]

        # initial cleanup
        self.delete_duplicate_captures_and_doc_refs()
        indices_mapping = self.get_indices_stats()
        self.offer_backup_restoration(maps=indices_mapping)

        # use timezone-aware datetime without colon and lowercase (opensearch rules)
        _timestamp = datetime.now(UTC).strftime("%Y-%m-%d_t_%H-%M-%S")
        backup_index_name = f"{self.index_name}-backup-{_timestamp}"
        self.backup_index(backup_index_name=backup_index_name)

        try:
            return self.attempt_reindexing(backup_index_name=backup_index_name)
        except Exception as err:
            log.error(f"Uncaught error during reindex: {err!s}")
            self.rollback_index(
                backup_index_name=backup_index_name,
            )
            raise

    def offer_backup_restoration(
        self,
        maps: dict[str, dict[str, Any]],
    ) -> None:
        """Offers to restore a backed up index if found to have more documents."""
        target_index_doc_count = self._get_doc_count()
        backups_of_target_index = [
            name for name in maps if name.startswith(f"{self.index_name}-backup-")
        ]
        if not backups_of_target_index:
            # no backups found
            return

        backup_doc_counts = {
            name: self._get_doc_count() for name in backups_of_target_index
        }
        max_backup_name, max_backup_count = max(
            backup_doc_counts.items(),
            key=lambda item: item[1],
        )

        if max_backup_count <= target_index_doc_count:
            # no good restoration candidate
            return

        log.warning(
            f"WARNING: '{self.index_name}' has a backup '{max_backup_name}' with "
            f"more docs than it ({max_backup_count} > {target_index_doc_count})",
        )
        response = (
            input(
                f"Would you like to restore '{self.index_name}' "
                f"from its backup '{max_backup_name}' before continuing? (y/N): ",
            )
            .strip()
            .lower()
        )

        if response == "y":
            self._restore_index_from_backup(
                backup_index_name=max_backup_name,
            )

    def rollback_index(
        self,
        backup_index_name: str,
    ):
        """Restore an index from a backup, setting it as self.index_name."""
        log.info(
            f"Restoring index '{self.index_name}' to its original state...",
        )
        self.delete_index(self.index_name)
        self._clone_index(source_index=backup_index_name, target_index=self.index_name)
        log.success(
            f"Successfully RESET {self.index_name} to its original form.",
        )

    def _ask_confirmation_and_rollback(
        self,
        backup_index_name: str,
        reasons: list[str],
    ) -> None:
        """Asks for confirmation before rollbacking the index.

        Used when a partially successful reindexing operation, giving the user
        the option to rollback to the backup index or to retain the current state.
        """
        log.error(
            f"Reindex verification failed for '{self.index_name}' with reasons:",
        )
        for reason in reasons:
            log.error(f" - {reason}")
        rollback_index = (
            input(
                "Would you like to reset the index to its original form? (Y/n): ",
            ).lower()
            or "y"
        ) == "y"
        if rollback_index:
            self.rollback_index(backup_index_name=backup_index_name)
        else:
            log.warning(
                f"Keeping backup index {backup_index_name} for manual verification.",
            )

    def _clone_index(
        self,
        source_index: str,
        target_index: str,
    ) -> None:
        """Clones an OpenSearch index.

        Args:
            source_index: Name of the source index to clone from.
            target_index: Name of the target index to clone to.
        Raises:
            RequestError: If the source index does not exist or an error occurs.
            OpensearchConnectionError: If the client cannot connect to OpenSearch.
            Other OpenSearch errors, if any.
        """

        # check if target index already exists
        if self.client.indices.exists(index=target_index):
            raise_target_exists(target_index)

        try:
            # first block writes on the source index
            # clone only works from a read-only index
            try:
                self.client.indices.put_settings(
                    index=source_index,
                    body={"settings": {"index.blocks.write": True}},
                )
            except NotFoundError as err:
                raise RequestError(
                    404,
                    f"Source index '{source_index}' does not exist",
                    {"error": "index_not_found_exception"},
                ) from err

            self.client.indices.clone(index=source_index, target=target_index)

            log.success(
                f"Successfully CLONED {source_index} to {target_index}",
            )

        except (RequestError, OpensearchConnectionError) as err:
            log.error(f"Error cloning index: {err!s}")
            raise
        finally:
            # always re-enable writes on the source index
            self.client.indices.put_settings(
                index=source_index,
                body={"settings": {"index.blocks.write": False}},
            )

    def _delete_captures_with_only_missing_files(
        self,
    ) -> None:
        """Delete captures that have only missing files (should not exist).

        Run this after the reindex operation to make sure the database is clean.
        """
        log.warning(
            "Deleting captures with only missing files...",
        )
        log.warning(
            f"Capture cleanup for index '{self.index_name}'...",
        )
        captures = Capture.objects.filter(
            index_name=self.index_name,
            is_deleted=False,
            capture_type=self.capture_type,
        )
        if not captures:
            log.info("No captures to delete.")
            return

        marked_for_deletion: list[Capture] = []
        for capture in captures:
            all_files = cast("QuerySet[File]", get_capture_files(capture, is_deleted=True))
            has_files = all_files and all_files.count() > 0
            has_files_but_all_missing = has_files and all(
                file_obj.is_deleted for file_obj in all_files
            )
            if has_files_but_all_missing:
                marked_for_deletion.append(capture)
            # Note that captures without any files are NOT marked for deletion.
            # This is to facilitate tests and to reduce the impact of the index
            # replacement procedure.
        if not marked_for_deletion:
            return

        log.warning(
            f"Deleting {len(marked_for_deletion)} captures "
            "that only have missing files linked to them.",
        )

        # remove capture references in index
        for capture in marked_for_deletion:
            self._delete_doc_by_capture_uuid(capture_uuid=capture.uuid)

        # remove captures from DB
        Capture.objects.filter(
            uuid__in=[capture.uuid for capture in marked_for_deletion],
        ).delete()

        log.success(
            f"Successfully deleted {len(marked_for_deletion)} captures.",
        )

    def _delete_doc_by_capture_uuid(
        self,
        capture_uuid: str,
    ) -> None:
        """Delete an OpenSearch document based on capture UUID."""
        try:
            # try to get the document
            self.client.get(index=self.index_name, id=capture_uuid)
        except NotFoundError:
            log.warning(
                f"Document by capture UUID: '{capture_uuid}' not found",
            )
            return
        else:
            self.client.delete(index=self.index_name, id=capture_uuid)

    def _find_duplicate_captures(self) -> dict[tuple[str], QuerySet[Capture]]:
        """Find duplicate captures in the database.

        Uses per-capture type logic to find duplicates.
        Returns:
            A dictionary of duplicate capture groups, where the key is a tuple
            of common attributes for the captures in the group,
            and the value is a queryset of the captures in that group.
        """
        # get all captures in the index
        captures = Capture.objects.filter(
            index_name=self.index_name,
            is_deleted=False,
            capture_type=self.capture_type,
        )
        duplicate_capture_groups = {}

        # get rh captures that have the same scan_group
        match self.capture_type:
            case CaptureType.RadioHound:
                duplicate_pairs = (
                    captures.values("owner", "scan_group")
                    .annotate(count=Count("uuid"))
                    .filter(count__gt=1)
                    .values_list("owner", "scan_group")
                )

                for owner, scan_group in duplicate_pairs:
                    duplicate_capture_groups[(owner, scan_group)] = captures.filter(
                        owner=owner,
                        scan_group=scan_group,
                    ).order_by("created_at")
            case CaptureType.DigitalRF:
                duplicate_pairs = (
                    captures.values("owner", "channel", "top_level_dir")
                    .annotate(count=Count("uuid"))
                    .filter(count__gt=1)
                    .values_list("owner", "channel", "top_level_dir")
                )

                for owner, channel, top_level_dir in duplicate_pairs:
                    duplicate_capture_groups[(owner, channel, top_level_dir)] = (
                        captures.filter(
                            owner=owner,
                            channel=channel,
                            top_level_dir=top_level_dir,
                        ).order_by("created_at")
                    )
            case _:
                log.error(f"Unknown capture type: {self.capture_type}")

        return duplicate_capture_groups

    def _get_doc_count(self, target_index: str | None = None) -> int:
        """Get the number of documents in an index.

        Args:
            target_index: Name of the index to get the document count for.
                If None, defaults to the index_name attribute of the class.
        Returns:
            The number of documents in the index.
            -1 if the index does not exist or an error occurs.
        """
        index_name = target_index or self.index_name
        try:
            return self.client.count(index=index_name)["count"]
        except NotFoundError:
            log.error(f"Index '{index_name}' not found")
            return -1
        except OpensearchConnectionError as e:
            log.error(
                f"Connection error while accessing '{index_name}': {e!s}",
            )
            return -1
        except AuthenticationException as e:
            log.error(
                f"Authentication failed for '{index_name}': {e!s}",
            )
            return -1
        except (RequestError, ValueError) as e:
            log.error(
                f"Unexpected error getting count for '{index_name}': {e!s}",
            )
            return -1

    def _recreate_index(
        self,
    ) -> None:
        """Recreates the OpenSearch index."""
        log.info(f"Recreating index '{self.index_name}'...")
        new_index_config = {
            "mappings": get_mapping_by_capture_type(self.capture_type),
            "settings": {
                "index": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1,
                },
            },
        }

        self.delete_index(index_name=self.index_name)
        self.client.indices.create(index=self.index_name, body=new_index_config)
        self.client.indices.refresh(index=self.index_name)

        log.success(
            f"Successfully CREATED index '{self.index_name}'",
        )

    def _reindex_single_capture(self, capture: Capture) -> bool:
        """Reindex a capture."""
        log.warning(f"Reindexing capture manually: '{capture.uuid}'...")
        capture_viewset = CaptureViewSet()
        try:
            capture_viewset.ingest_capture(
                capture=capture,
                drf_channel=capture.channel,
                rh_scan_group=capture.scan_group,
                requester=capture.owner,
                top_level_dir=capture.top_level_dir,
            )

            # apply field transforms to search_props fields
            Transforms(
                capture_type=capture.capture_type,
            ).apply_field_transforms(
                index_name=capture.index_name,
                capture_uuid=str(capture.uuid),
            )

        except FileNotFoundError as e:
            log.error(f"File not found for capture '{capture.uuid}': {e!s}")
            return False
        except (RequestError, OpensearchConnectionError) as e:
            log.error(f"Error reindexing capture '{capture.uuid}': {e!s}")
            log.warning(f"Skipping capture '{capture.uuid}'...")
            return False
        else:
            return True

    def _reindex_valid_captures(
        self,
    ) -> None:
        """Reindexes captures individually, by re-linking files."""
        captures_to_reindex = Capture.objects.filter(
            capture_type=self.capture_type,
            index_name=self.index_name,
            is_deleted=False,
        )

        log.info(
            "# of captures to reindex: "
            f"{captures_to_reindex.count()} / {Capture.objects.all().count()}",
        )

        failed_captures = []
        successful_captures = []
        for capture in captures_to_reindex:
            capture_reindexed = self._reindex_single_capture(
                capture=capture,
            )
            if not capture_reindexed:
                failed_captures.append(capture)
            else:
                successful_captures.append(capture)

        log.success(
            f"Successfully REINDEXED {len(successful_captures)}"
            f" / {captures_to_reindex.count()} captures",
        )
        if failed_captures:
            log.warning(
                "Failed to reindex "
                f"{len(failed_captures)} / {captures_to_reindex.count()}"
                f" captures",
            )
            for capture in failed_captures:
                log.warning(f"Failed to reindex capture '{capture.uuid}'")

    def _restore_index_from_backup(
        self,
        backup_index_name: str,
    ) -> None:
        """Restores an index from one of its backups."""
        log.info(
            f"Restoring index '{self.index_name}' from backup '{backup_index_name}'...",
        )
        self.delete_index(index_name=self.index_name)
        self._clone_index(
            source_index=backup_index_name,
            target_index=self.index_name,
        )
        log.success(
            f"Successfully RESTORED {self.index_name} from {backup_index_name}",
        )
        self.client.indices.refresh(index=self.index_name)

    def _was_reindexing_successful(
        self,
    ) -> tuple[bool, list[str]]:
        """Checks the database is consistent with this index state.

        Args:
            index_name: Name of the index to check
            client:     OpenSearch client
        Returns:
            Whether the index is consistent with database
            A list of reasons it is not (if any)
        """
        self.client.indices.refresh(index=self.index_name)
        valid_captures = Capture.objects.filter(
            index_name=self.index_name,
            is_deleted=False,
        )
        capture_uuids_from_db = {
            str(uuid) for uuid in valid_captures.values_list("uuid", flat=True)
        }
        try:
            all_docs = self.client.search(
                index=self.index_name,
                size=MAX_OS_SIZE,  # pyright: ignore[reportCallIssue]
            )
        except RequestError as e:
            log.error(f"Error searching index: {e!s}")
            return False, []
        capture_uuids_from_opensearch = {
            str(doc["_id"]) for doc in all_docs["hits"]["hits"]
        }

        # make sure we're fetching all document IDs from this index
        if len(capture_uuids_from_opensearch) > 0.9 * MAX_OS_SIZE:
            log.warning(
                f"Approaching OpenSearch search size limit of {MAX_OS_SIZE} docs:"
                " we'll need to write a lazy-loaded approach soon.",
            )
        assert self._get_doc_count() == len(capture_uuids_from_opensearch), (
            "Document count does not match the number of documents in the index: "
            f"{self._get_doc_count()} != "
            f"{len(capture_uuids_from_opensearch)}"
        )

        missing_from_opensearch = capture_uuids_from_db - capture_uuids_from_opensearch
        missing_from_db = capture_uuids_from_opensearch - capture_uuids_from_db
        if not missing_from_opensearch and not missing_from_db:
            return True, []
        reasons: list[str] = []
        if missing_from_opensearch:
            reasons += [
                f"Missing from OpenSearch:\t'{uuid}'"
                for uuid in missing_from_opensearch
            ]
        if missing_from_db:
            reasons += [f"Missing from DB:\t\t'{uuid}'" for uuid in missing_from_db]
        return False, reasons

    def __combine_scripts(self, transform_scripts: dict[str, dict[str, str]]) -> str:
        """Combine transform scripts into one source string."""
        return ";".join([script["source"] for script in transform_scripts.values()])

    def __reindex_with_mapping(
        self,
        source_index: str,
        dest_index: str,
        capture_type: CaptureType,
    ) -> None:
        """Reindex documents with mapping changes.

        It uses the reindex API to reindex documents with mapping changes and it
            is kept here for reference, but is not used by handle().
        """
        try:
            # Get the transform scripts
            transform_scripts = Transforms(
                capture_type=capture_type,
            ).get_transform_scripts()

            # Perform reindex operation with combined transform scripts
            body = {
                "source": {"index": source_index},
                "dest": {"index": dest_index},
                "script": {
                    "source": self.__combine_scripts(transform_scripts),
                    "lang": "painless",
                },
            }

            self.client.reindex(body=body)
            self.client.indices.refresh(index=dest_index)
            log.success(
                f"Successfully REINDEXED from {source_index} to {dest_index}",
            )

        except RequestError as err:
            failures = err.info.get("failures", [])
            log.error(f"Some documents failed to reindex: {failures}")

            # prompt input to reindex the failed documents
            manual_reindex = (
                input("Reindex failed documents manually? (y/N): ").lower() == "y"
            )
            log.warning(f"Manual reindex: {manual_reindex}")
            if not manual_reindex:
                return
            log.warning("Reindexing failed documents manually...")

            # manually index the failed documents, skipping deleted captures
            failed_captures = []
            success_captures = []
            for failure in failures:
                capture = Capture.objects.get(uuid=failure["id"])
                if capture.is_deleted:
                    continue
                reindexed = self._reindex_single_capture(capture=capture)
                if not reindexed:
                    failed_captures.append(capture)
                else:
                    success_captures.append(capture)

            if failed_captures:
                log.warning(
                    f"Failed to reindex {len(failed_captures)} "
                    f"captures: {failed_captures}",
                )
            log.success(
                f"Successfully REINDEXED {len(success_captures)} captures",
            )


def raise_target_exists(target_index: str) -> NoReturn:
    raise RequestError(
        400,
        f"Target index '{target_index}' already exists",
        {"error": "index_already_exists_exception"},
    )
