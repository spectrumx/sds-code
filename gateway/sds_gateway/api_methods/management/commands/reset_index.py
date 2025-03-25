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
                if (ctx._source.capture_props != null) {
                    if (ctx._source.capture_props.latitude != null &&
                    ctx._source.capture_props.longitude != null &&
                    ctx._source.capture_props.coordinates == null) {
                        ctx._source.capture_props.coordinates = [
                            ctx._source.capture_props.longitude,
                            ctx._source.capture_props.latitude
                        ];
                    }
                }
            """,
            "lang": "painless",
        }
    }

    def add_arguments(self, parser):
        parser.add_argument(
            "--index-name",
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
        """Compare mappings and return list of new fields."""
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
                    self.stdout.write(f"Applying transform for field '{field}'...")

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

    def reindex_single_capture(self, capture: Capture) -> bool | None:
        """Reindex a capture."""
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

    def reindex_with_mapping(
        self, client: OpenSearch, source_index: str, dest_index: str
    ):
        """Reindex documents with mapping changes."""
        try:
            # Perform reindex operation
            body = {"source": {"index": source_index}, "dest": {"index": dest_index}}

            response = client.reindex(body=body)

            if response.get("failures"):
                self.stdout.write(
                    self.style.ERROR(
                        f"Some documents failed to reindex: {response['failures']}"
                    )
                )

                # prompt input to reindex the failed documents
                manual_reindex = (
                    input("Reindex failed documents manually? (y/N): ").lower() == "y"
                )
                if manual_reindex == "y":
                    # manually index the failed documents, skipping deleted captures
                    for failure in response["failures"]:
                        capture = Capture.objects.get(uuid=failure["_id"])
                        if not capture.is_deleted:
                            self.reindex_single_capture(capture)
            else:
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

    def clone_index_mapping(
        self, client: OpenSearch, source_index: str, dest_index: str
    ):
        """Create a new index using mapping from an existing index."""
        try:
            # Get mapping from source index
            mapping = client.indices.get_mapping(index=source_index)
            source_mapping = mapping[source_index]["mappings"]

            # Create new index with the same mapping
            create_response = client.indices.create(
                index=dest_index, body={"mappings": source_mapping}
            )

            if create_response.get("acknowledged"):
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully created {dest_index} "
                        f"with mapping from {source_index}"
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"Index created but not acknowledged: {create_response}"
                    )
                )

        except (RequestError, OpensearchConnectionError, NotFoundError) as e:
            self.stdout.write(self.style.ERROR(f"Error cloning index mapping: {e!s}"))

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
        self.clone_index_mapping(client, index_name, backup_index_name)

        # Verify backup was successful
        backup_count = self.get_doc_count(client, backup_index_name)
        if backup_count != original_count:
            self.stdout.write(
                self.style.ERROR(
                    f"Backup verification failed for {index_name}! "
                    f"Original: {original_count}, Backup: {backup_count}"
                )
            )

            # Ask user whether to proceed
            proceed = (
                input("Document counts don't match. Proceed anyway? (y/N): ").lower()
                == "y"
            )
            if not proceed:
                msg = (
                    f"Skipping {index_name}. "
                    f"Backup index {backup_index_name} preserved."
                )
                self.stdout.write(self.style.WARNING(msg))
                return

        # delete original index and recreate it with new mapping
        self.delete_index(client, index_name)
        self.create_index(client, index_name, new_index_config)

        # reindex from backup index to original index
        self.reindex_with_mapping(client, backup_index_name, index_name)

        # Verify reindex was successful
        new_count = self.get_doc_count(client, index_name)
        if new_count != original_count:
            self.stdout.write(
                self.style.ERROR(
                    f"Reindex verification failed for {index_name}! "
                    f"Original: {original_count}, New: {new_count}"
                )
            )
            self.stdout.write(
                self.style.WARNING(
                    f"Keeping backup index {backup_index_name} for manual verification."
                )
            )
            return

        # Only delete backup if document counts match
        self.delete_index(client, backup_index_name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated {index_name} with {new_count} documents"
            )
        )
