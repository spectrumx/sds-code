"""Django management command to initialize OpenSearch indices."""

from datetime import UTC
from datetime import datetime

from django.core.management.base import BaseCommand
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
    """Initialize OpenSearch indices for different capture types."""

    help = "Initialize or update OpenSearch indices with mappings"

    # Define transform scripts for different field updates
    field_transforms = {
        "capture_props.coordinates": {
            "source": """
                if (ctx._source.capture_props.latitude != null &&
                    ctx._source.capture_props.longitude != null &&
                    ctx._source.capture_props.coordinates == null) {
                    ctx._source.capture_props.coordinates = [
                        ctx._source.capture_props.longitude,
                        ctx._source.capture_props.latitude
                    ];
                }
            """.strip(),
            "lang": "painless",
        }
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

    def get_new_fields(
        self, client: OpenSearch, old_index: str, new_index: str
    ) -> list:
        """Compare mappings and return list of new fields not in old mapping."""
        try:
            old_mapping = client.indices.get_mapping(index=old_index)[old_index][
                "mappings"
            ]
            new_mapping = client.indices.get_mapping(index=new_index)[new_index][
                "mappings"
            ]

            # Helper function to flatten nested mappings
            def flatten_mapping(mapping: dict, prefix="") -> set:
                fields = set()
                for key, value in mapping.get("properties", {}).items():
                    full_path = f"{prefix}{key}" if prefix else key
                    if "properties" in value:
                        fields.update(flatten_mapping(value, f"{full_path}."))
                    else:
                        fields.add(full_path)
                return fields

            old_fields = flatten_mapping(old_mapping)
            new_fields = flatten_mapping(new_mapping)

            return list(new_fields - old_fields)

        except (NotFoundError, RequestError, OpensearchConnectionError) as e:
            self.stdout.write(self.style.ERROR(f"Error comparing mappings: {e!s}"))
            return []

    def apply_field_transforms(self, client: OpenSearch, index_name: str, fields: list):
        """Apply transforms for new fields."""
        for field in fields:
            if field in self.field_transforms:
                try:
                    self.stdout.write(f"Applying transform for new field '{field}'...")

                    body = {"script": self.field_transforms[field]}

                    response = client.update_by_query(
                        index=index_name, body=body, conflicts="proceed"
                    )

                    if response.get("failures"):
                        failures = response["failures"]
                        self.stdout.write(
                            self.style.WARNING(
                                f"Some updates failed for field '{field}': {failures}"
                            )
                        )
                    else:
                        updated = response["updated"]
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"Successfully transformed field '{field}' "
                                f"in {updated} documents"
                            )
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
            rh_scan_groups = captures.values_list("scan_group", flat=True)
            duplicate_scan_groups = rh_scan_groups.value_counts().loc[lambda x: x > 1]
            for scan_group in duplicate_scan_groups.index:
                duplicate_capture_groups[scan_group] = captures.filter(
                    scan_group=scan_group
                ).order_by("created_at")
        elif capture_type == CaptureType.DigitalRF:
            drf_channel_top_level_dirs = captures.values_list(
                "channel", "top_level_dir"
            )
            duplicate_channel_top_level_dirs = (
                drf_channel_top_level_dirs.value_counts().loc[lambda x: x > 1]
            )
            for channel, top_level_dir in duplicate_channel_top_level_dirs.index:
                duplicate_capture_groups[(channel, top_level_dir)] = captures.filter(
                    channel=channel, top_level_dir=top_level_dir
                ).order_by("created_at")

        return duplicate_capture_groups

    def delete_duplicate_captures(
        self, client: OpenSearch, capture_type: CaptureType, index_name: str
    ):
        """Delete duplicate captures from an index."""
        duplicate_capture_groups = self.find_duplicate_captures(
            capture_type, index_name
        )

        # delete duplicate rh captures
        for capture_group in duplicate_capture_groups.values():
            # assert that the capture group is sorted by created_at
            assert capture_group.sort_values("created_at").equals(capture_group), (
                "Capture group is not sorted by created_at"
            )

            # assert that the first capture is the oldest
            assert capture_group.iloc[0].created_at == capture_group.created_at.min(), (
                "First capture is not the oldest"
            )

            if capture_type == CaptureType.RadioHound:
                # assert that the captures in the group belong to the same scan_group
                assert capture_group.scan_group.nunique() == 1, (
                    "Captures in the group do not belong to the same scan_group"
                )
            elif capture_type == CaptureType.DigitalRF:
                # assert that the captures in the group belong
                # to the same channel and top_level_dir
                assert capture_group.channel.nunique() == 1, (
                    "Captures in the group do not belong to the same channel"
                )
                assert capture_group.top_level_dir.nunique() == 1, (
                    "Captures in the group do not belong to the same top_level_dir"
                )

            # keep the first capture and delete the rest
            for capture in capture_group[1:]:
                # assert that the capture is not the oldest capture in the group
                assert capture.created_at != capture_group.created_at.min(), (
                    "Capture is the oldest capture in the group"
                )

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
        """Delete a document by capture UUID."""
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

    def reindex_with_mapping(
        self, client: OpenSearch, source_index: str, dest_index: str
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

            # Check for new fields and apply transforms
            new_fields = self.get_new_fields(client, source_index, dest_index)
            if new_fields:
                self.stdout.write(f"Found new fields: {new_fields}")
                self.apply_field_transforms(client, dest_index, new_fields)

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
        client: OpenSearch = get_opensearch_client()
        capture_type = options["capture_type"]
        index_name = options["index_name"]

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

        # Use timezone-aware datetime
        timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
        backup_index_name = f"{index_name}-backup-{timestamp}"

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
            self.stdout.write(self.style.ERROR(f"Failed to create backup index: {e!s}"))
            return

        # delete original index and recreate it with new mapping
        self.delete_index(client, index_name)
        self.create_index(client, index_name, new_index_config)

        # reindex captures
        for capture in captures:
            self.reindex_single_capture(capture)

        # Verify reindex was successful
        new_count = self.get_doc_count(client, index_name)
        if new_count != original_count:
            self.stdout.write(
                self.style.ERROR(
                    f"Reindex verification failed for {index_name}! "
                    f"Original: {original_count}, New: {new_count}"
                )
            )
            recall_index_mapping = (
                input(
                    "Would you like to reset the index to its original form? (y/N): "
                ).lower()
                == "y"
            )
            if recall_index_mapping:
                self.delete_index(client, index_name)
                self.clone_index(client, backup_index_name, index_name)
                self.delete_index(client, backup_index_name)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully reset {index_name} to its original form."
                    )
                )
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
