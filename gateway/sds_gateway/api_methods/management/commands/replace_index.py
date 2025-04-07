"""Django management command to initialize OpenSearch indices."""

from datetime import UTC
from datetime import datetime

from django.core.management.base import BaseCommand
from django.db.models import Count
from opensearchpy import AuthenticationException
from opensearchpy import ConnectionError as OpensearchConnectionError
from opensearchpy import NotFoundError
from opensearchpy import OpenSearch
from opensearchpy import RequestError

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet


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

    # Define transform scripts for different field updates
    rh_field_transforms = {
        "search_props.center_frequency": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.center_frequency != null) {
                    ctx._source.search_props.center_frequency =
                        ctx._source.capture_props.center_frequency;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.frequency_min": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.metadata != null &&
                    ctx._source.capture_props.metadata.fmin != null) {
                    ctx._source.search_props.frequency_min =
                        ctx._source.capture_props.metadata.fmin;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.frequency_max": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.metadata != null &&
                    ctx._source.capture_props.metadata.fmax != null) {
                    ctx._source.search_props.frequency_max =
                        ctx._source.capture_props.metadata.fmax;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.span": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.span != null) {
                    ctx._source.search_props.span = ctx._source.capture_props.span;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.gain": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.gain != null) {
                    ctx._source.search_props.gain = ctx._source.capture_props.gain;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.coordinates": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.latitude != null &&
                    ctx._source.capture_props.longitude != null) {
                    ctx._source.search_props.coordinates = [
                        ctx._source.capture_props.longitude,
                        ctx._source.capture_props.latitude
                    ];
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.sample_rate": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.sample_rate != null) {
                    ctx._source.search_props.sample_rate =
                        ctx._source.capture_props.sample_rate;
                }
            """.strip(),
            "lang": "painless",
        },
    }

    drf_field_transforms = {
        "search_props.center_frequency": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.center_freq != null) {
                    ctx._source.search_props.center_frequency =
                        ctx._source.capture_props.center_freq;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.frequency_min": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.center_freq != null &&
                    ctx._source.capture_props.span != null &&
                    ctx._source.search_props.frequency_min == null) {
                    ctx._source.search_props.frequency_min =
                        ctx._source.capture_props.center_freq -
                        (ctx._source.capture_props.span / 2);
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.frequency_max": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.center_freq != null &&
                    ctx._source.capture_props.span != null &&
                    ctx._source.search_props.frequency_max == null) {
                    ctx._source.search_props.frequency_max =
                        ctx._source.capture_props.center_freq +
                        (ctx._source.capture_props.span / 2);
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.start_time": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.start_bound != null &&
                    ctx._source.search_props.start_time == null) {
                    ctx._source.search_props.start_time =
                        ctx._source.capture_props.start_bound;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.end_time": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.end_bound != null &&
                    ctx._source.search_props.end_time == null) {
                    ctx._source.search_props.end_time =
                        ctx._source.capture_props.end_bound;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.span": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.span != null &&
                    ctx._source.search_props.span == null) {
                    ctx._source.search_props.span = ctx._source.capture_props.span;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.gain": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.gain != null &&
                    ctx._source.search_props.gain == null) {
                    ctx._source.search_props.gain = ctx._source.capture_props.gain;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.bandwidth": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.bandwidth != null &&
                    ctx._source.search_props.bandwidth == null) {
                    ctx._source.search_props.bandwidth =
                        ctx._source.capture_props.bandwidth;
                }
            """.strip(),
            "lang": "painless",
        },
        "search_props.sample_rate": {
            "source": """
                if (ctx._source.capture_props != null &&
                    ctx._source.capture_props.sample_rate_numerator != null &&
                    ctx._source.capture_props.sample_rate_denominator != null &&
                    ctx._source.search_props.sample_rate == null) {
                    ctx._source.search_props.sample_rate =
                        ctx._source.capture_props.sample_rate_numerator /
                        ctx._source.capture_props.sample_rate_denominator;
                }
            """.strip(),
            "lang": "painless",
        },
    }

    def add_arguments(self, parser):
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

    def get_transform_scripts(self, capture_type: CaptureType) -> dict:
        """Get the transform scripts based on capture type."""
        if capture_type == CaptureType.RadioHound:
            return self.rh_field_transforms
        if capture_type == CaptureType.DigitalRF:
            return self.drf_field_transforms
        self.stdout.write(self.style.WARNING(f"Unknown capture type: {capture_type}"))
        return {}

    def init_search_props(self, client: OpenSearch, index_name: str, capture_uuid: str):
        """Initialize the search_props field."""
        try:
            self.stdout.write(
                f"Initializing search_props for capture '{capture_uuid}'..."
            )

            init_script = {
                "script": {
                    "source": """
                    if (ctx._source.search_props == null) {
                        ctx._source.search_props = new HashMap();
                    }
                    """.strip(),
                    "lang": "painless",
                }
            }

            response = client.update(
                index=index_name, id=capture_uuid, body=init_script
            )
            self.stdout.write(f"Update response: {response}")
        except (RequestError, OpensearchConnectionError) as e:
            self.stdout.write(
                self.style.ERROR(f"Error initializing search_props: {e!s}")
            )

    def apply_field_transforms(
        self,
        client: OpenSearch,
        index_name: str,
        field_transforms: dict,
        capture_uuid: str,
    ):
        """Apply transforms for new fields.

        Args:
            client: OpenSearch client
            index_name: Name of the index to apply transforms to
            field_transforms: Dictionary of field transforms to apply
            capture_uuid: UUID of the specific capture to transform.
        """
        # initialize the search_props field on the document
        # (presumes it doesn't exist)
        self.init_search_props(client, index_name, capture_uuid)

        for field, transform in field_transforms.items():
            try:
                self.stdout.write(f"Applying transform for field '{field}'...")
                # update the document with script
                try:
                    response = client.update(
                        index=index_name,
                        id=capture_uuid,
                        body={
                            "script": {
                                "source": transform["source"],
                                "lang": transform["lang"],
                            }
                        },
                    )
                    self.stdout.write(f"Update response: {response}")
                    self.stdout.write(
                        self.style.SUCCESS(f"Successfully transformed field '{field}'")
                    )
                except (RequestError, OpensearchConnectionError) as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error with direct update: {e!s}")
                    )

            except (RequestError, OpensearchConnectionError) as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error applying transform for field '{field}': {e!s}"
                    )
                )

    def find_duplicate_captures(self, capture_type: CaptureType, index_name: str):
        """Find duplicate captures in the database."""
        # get all captures in the index
        captures = Capture.objects.filter(
            index_name=index_name,
            is_deleted=False,
            capture_type=capture_type,
        )
        duplicate_capture_groups = {}

        # get rh captures that have the same scan_group
        if capture_type == CaptureType.RadioHound:
            duplicate_scan_groups = (
                captures.values("scan_group")
                .annotate(count=Count("uuid"))
                .filter(count__gt=1)
                .values_list("scan_group", flat=True)
            )

            for scan_group in duplicate_scan_groups:
                duplicate_capture_groups[scan_group] = captures.filter(
                    scan_group=scan_group
                ).order_by("created_at")
        elif capture_type == CaptureType.DigitalRF:
            duplicate_pairs = (
                captures.values("channel", "top_level_dir")
                .annotate(count=Count("uuid"))
                .filter(count__gt=1)
            )

            for pair in duplicate_pairs:
                key = (pair["channel"], pair["top_level_dir"])
                duplicate_capture_groups[key] = captures.filter(
                    channel=pair["channel"], top_level_dir=pair["top_level_dir"]
                ).order_by("created_at")
        else:
            self.stdout.write(
                self.style.WARNING(f"Unknown capture type: {capture_type}")
            )

        return duplicate_capture_groups

    def delete_duplicate_captures(
        self, client: OpenSearch, capture_type: CaptureType, index_name: str
    ):
        """Delete duplicate captures from an index and database."""
        duplicate_capture_groups = self.find_duplicate_captures(
            capture_type, index_name
        )

        # if the dictionary is empty, return
        if not duplicate_capture_groups:
            self.stdout.write(self.style.WARNING("No duplicate captures found"))
            return

        # delete duplicate captures
        for capture_group in duplicate_capture_groups.values():
            # if the capture group is not sorted by created_at, sort it
            assert capture_group.order_by("created_at") == capture_group, (
                "Capture group is not sorted by created_at"
            )

            # Get the oldest capture's created_at
            oldest_created_at = capture_group.first().created_at

            # Get all captures except the oldest one
            duplicates_to_delete = capture_group.exclude(created_at=oldest_created_at)

            if capture_type == CaptureType.RadioHound:
                # Verify all captures have the same scan_group
                distinct_scan_groups = capture_group.values_list(
                    "scan_group", flat=True
                ).distinct()
                assert len(distinct_scan_groups) == 1, (
                    "Captures in the group do not belong to the same scan_group"
                )
            elif capture_type == CaptureType.DigitalRF:
                # Verify all captures have the same channel and top_level_dir
                distinct_channels = capture_group.values_list(
                    "channel", flat=True
                ).distinct()
                distinct_dirs = capture_group.values_list(
                    "top_level_dir", flat=True
                ).distinct()
                assert len(distinct_channels) == 1, (
                    "Captures in the group do not belong to the same channel"
                )
                assert len(distinct_dirs) == 1, (
                    "Captures in the group do not belong to the same top_level_dir"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"Unknown capture type: {capture_type}")
                )
                return

            # Delete all duplicates (keeping the oldest)
            for capture in duplicates_to_delete:
                self.stdout.write(
                    self.style.WARNING(
                        f"Deleting duplicate capture '{capture.uuid}'..."
                    )
                )
                self.delete_doc_by_capture_uuid(client, index_name, capture.uuid)
                capture.delete()

    def delete_doc_by_capture_uuid(
        self, client: OpenSearch, index_name: str, capture_uuid: str
    ):
        """Delete an OpenSearch document based on capture UUID."""
        try:
            # try to get the document
            client.get(index=index_name, id=capture_uuid)
        except NotFoundError:
            self.stdout.write(
                self.style.WARNING(
                    f"Document by capture UUID: '{capture_uuid}' not found"
                )
            )
            return
        else:
            self.stdout.write(
                self.style.WARNING(
                    f"Deleting document by capture UUID: '{capture_uuid}'..."
                )
            )
            client.delete(index=index_name, id=capture_uuid)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully deleted document by capture UUID: '{capture_uuid}'"
                )
            )

    def reindex_single_capture(self, capture: Capture) -> bool:
        """Reindex a capture."""
        self.stdout.write(
            self.style.WARNING(f"Reindexing capture manually: '{capture.uuid}'...")
        )
        capture_viewset = CaptureViewSet()
        try:
            capture_viewset.ingest_capture(
                capture=capture,
                drf_channel=capture.channel,
                rh_scan_group=capture.scan_group,
                requester=capture.owner,
                top_level_dir=capture.top_level_dir,
            )

            # Apply field transforms for this specific capture
            client = get_opensearch_client()
            transform_scripts = self.get_transform_scripts(capture.capture_type)
            if transform_scripts:
                self.apply_field_transforms(
                    client=client,
                    index_name=capture.index_name,
                    field_transforms=transform_scripts,
                    capture_uuid=str(capture.uuid),
                )
        except (RequestError, OpensearchConnectionError) as e:
            self.stdout.write(
                self.style.ERROR(f"Error reindexing capture '{capture.uuid}': {e!s}")
            )
            self.stdout.write(
                self.style.WARNING(f"Skipping capture '{capture.uuid}'...")
            )
            return False
        else:
            return True

    def delete_index(self, client: OpenSearch, index_name: str):
        """Delete an index."""
        self.stdout.write(f"Deleting index '{index_name}'...")
        client.indices.delete(index=index_name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted index '{index_name}'",
            ),
        )

    def create_index(self, client: OpenSearch, index_name: str, index_config: dict):
        """Create an index."""
        self.stdout.write(f"Creating index '{index_name}'...")
        client.indices.create(index=index_name, body=index_config)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created index '{index_name}'",
            ),
        )

    def clone_index(self, client: OpenSearch, source_index: str, target_index: str):
        """Clone an index."""

        def raise_target_exists():
            raise RequestError(
                400,
                f"Target index '{target_index}' already exists",
                {"error": "index_already_exists_exception"},
            )

        try:
            # Check if target index already exists
            if client.indices.exists(index=target_index):
                raise_target_exists()

            # First block writes on the source index
            # Clone only works from a read-only index
            try:
                client.indices.put_settings(
                    index=source_index, body={"settings": {"index.blocks.write": True}}
                )
            except NotFoundError as e:
                raise RequestError(
                    404,
                    f"Source index '{source_index}' does not exist",
                    {"error": "index_not_found_exception"},
                ) from e

            # Clone the index
            client.indices.clone(index=source_index, target=target_index)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully cloned {source_index} to {target_index}"
                )
            )

        except (RequestError, OpensearchConnectionError) as e:
            self.stdout.write(self.style.ERROR(f"Error cloning index: {e!s}"))
            raise
        finally:
            # Always re-enable writes on the source index
            client.indices.put_settings(
                index=source_index, body={"settings": {"index.blocks.write": None}}
            )

    def rollback_index(
        self, client: OpenSearch, index_name: str, backup_index_name: str
    ):
        """Restore an index from a backup."""
        self.stdout.write(f"Restoring index '{index_name}' to its original state...")
        self.delete_index(client, index_name)
        self.clone_index(client, backup_index_name, index_name)
        self.stdout.write(
            self.style.SUCCESS(f"Successfully reset {index_name} to its original form.")
        )

    def reindex_with_mapping(
        self,
        client: OpenSearch,
        source_index: str,
        dest_index: str,
        capture_type: CaptureType,
    ):
        """Reindex documents with mapping changes."""
        try:
            # Perform reindex operation
            body = {"source": {"index": source_index}, "dest": {"index": dest_index}}

            client.reindex(body=body)

            # Refresh destination index to make documents searchable
            client.indices.refresh(index=dest_index)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully reindexed from {source_index} to {dest_index}"
                )
            )

            # Apply field transforms
            transform_scripts = self.get_transform_scripts(capture_type)
            if transform_scripts:
                self.apply_field_transforms(client, dest_index, transform_scripts)
            else:
                self.stdout.write(self.style.WARNING("No field transforms to apply"))

        except (RequestError, OpensearchConnectionError, NotFoundError) as e:
            self.stdout.write(self.style.ERROR(f"Error during reindex: {e!s}"))
            if isinstance(e, RequestError) and e.info.get("failures"):
                self.stdout.write(
                    self.style.ERROR(
                        f"Some documents failed to reindex: {e.info['failures']}"
                    )
                )

                # prompt input to reindex the failed documents
                manual_reindex = (
                    input("Reindex failed documents manually? (y/N): ").lower() == "y"
                )
                self.stdout.write(
                    self.style.WARNING(f"Manual reindex: {manual_reindex}")
                )
                if manual_reindex:
                    self.stdout.write(
                        self.style.WARNING("Reindexing failed documents manually...")
                    )

                    # manually index the failed documents, skipping deleted captures
                    for failure in e.info["failures"]:
                        capture = Capture.objects.get(uuid=failure["id"])
                        if not capture.is_deleted:
                            self.reindex_single_capture(capture)

    def get_doc_count(self, client: OpenSearch, index_name: str) -> int:
        """Get the number of documents in an index."""
        try:
            return client.count(index=index_name)["count"]
        except NotFoundError:
            self.stdout.write(self.style.ERROR(f"Index '{index_name}' not found"))
            return -1
        except OpensearchConnectionError as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Connection error while accessing '{index_name}': {e!s}"
                )
            )
            return -1
        except AuthenticationException as e:
            self.stdout.write(
                self.style.ERROR(f"Authentication failed for '{index_name}': {e!s}")
            )
            return -1
        except (RequestError, ValueError) as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Unexpected error getting count for '{index_name}': {e!s}"
                )
            )
            return -1

    def handle(self, *args, **options):
        """Execute the command."""
        response = input(
            "WARNING: This command is potentially destructive to existing "
            "Capture and OpenSearch index data and should be used with "
            "extreme caution.\n"
            "Are you sure you want to continue? (y/N): "
        ).lower()
        if response != "y":
            self.stdout.write(self.style.WARNING("Command cancelled."))
            return

        client: OpenSearch = get_opensearch_client()
        capture_type = options["capture_type"]
        index_name = options["index_name"]

        # Use timezone-aware datetime
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup_index_name = f"{index_name}-backup-{timestamp}"

        try:
            # delete duplicate captures, including docs in the original index
            self.delete_duplicate_captures(client, capture_type, index_name)

            # get queryset of captures to reindex
            captures = Capture.objects.filter(
                capture_type=capture_type,
                index_name=index_name,
                is_deleted=False,
            )

            new_index_config = {
                "mappings": get_mapping_by_capture_type(capture_type),
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 1,
                    },
                },
            }

            # Get original document count
            original_count = self.get_doc_count(client, index_name)
            if original_count < 0:
                self.stdout.write(
                    self.style.ERROR(f"Skipping {index_name} due to count error")
                )
                return

            # create backup index with same mapping
            try:
                self.clone_index(client, index_name, backup_index_name)
            except (RequestError, OpensearchConnectionError) as e:
                self.stdout.write(
                    self.style.ERROR(f"Failed to create backup index: {e!s}")
                )
                return

            # delete original index and recreate it with new mapping
            self.delete_index(client, index_name)
            self.create_index(client, index_name, new_index_config)

            # reindex captures
            for capture in captures:
                self.reindex_single_capture(capture)

            # Refresh newn index to make documents searchable
            client.indices.refresh(index=index_name)

            # Verify reindex was successful
            new_count = self.get_doc_count(client, index_name)
            if new_count != original_count:
                self.stdout.write(
                    self.style.ERROR(
                        f"Reindex verification failed for {index_name}! "
                        f"Original: {original_count}, New: {new_count}"
                    )
                )
                rollback_index = (
                    input(
                        "Would you like to reset the index "
                        "to its original form? (Y/n): ",
                    ).lower()
                    or "y"
                ) == "y"
                if rollback_index:
                    self.rollback_index(client, index_name, backup_index_name)
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Keeping backup index {backup_index_name} "
                            "for manual verification."
                        )
                    )
                return

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully updated {index_name} with {new_count} documents"
                )
            )
        except Exception as e:  # noqa: BLE001
            self.stdout.write(self.style.ERROR(f"Error during reindex: {e!s}"))
            self.rollback_index(client, index_name, backup_index_name)
