"""Django management command to initialize OpenSearch indices."""

from datetime import UTC
from datetime import datetime
from typing import Any
from typing import NoReturn
from typing import cast

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.db.models import QuerySet
from opensearchpy import AuthenticationException
from opensearchpy import ConnectionError as OpensearchConnectionError
from opensearchpy import NotFoundError
from opensearchpy import OpenSearch
from opensearchpy import RequestError

from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.models import File
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
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

    def get_transform_scripts(
        self,
        capture_type: CaptureType,
    ) -> dict[str, dict[str, str]]:
        """Get the transform scripts based on capture type."""
        match capture_type:
            case CaptureType.RadioHound:
                return self.rh_field_transforms
            case CaptureType.DigitalRF:
                return self.drf_field_transforms
            case _:
                self.stdout.write(
                    self.style.ERROR(
                        f"Unknown capture type: {capture_type}",
                    ),
                )
                return {}

    def init_search_props(
        self,
        client: OpenSearch,
        index_name: str,
        capture_uuid: str,
    ) -> None:
        """Initialize the search_props field."""
        try:
            self.stdout.write(
                f"Initializing search_props for capture '{capture_uuid}'...",
            )

            init_script = {
                "script": {
                    "source": """
                    if (ctx._source.search_props == null) {
                        ctx._source.search_props = new HashMap();
                    }
                    """.strip(),
                    "lang": "painless",
                },
            }

            _response = client.update(
                index=index_name,
                id=capture_uuid,
                body=init_script,
            )
            if _response.get("result") != "updated":
                self.stdout.write(
                    self.style.ERROR(
                        "Failed to initialize search_props for "
                        f"cap={capture_uuid}: {_response!s}",
                    ),
                )
        except (RequestError, OpensearchConnectionError) as e:
            self.stdout.write(
                self.style.ERROR(f"Error initializing search_props: {e!s}"),
            )

    def apply_field_transforms(
        self,
        client: OpenSearch,
        index_name: str,
        field_transforms: dict[str, dict[str, str]],
        capture_uuid: str,
    ) -> None:
        """Apply transforms for new fields.

        Args:
            client: OpenSearch client
            index_name: Name of the index to apply transforms to
            field_transforms: Dictionary of field transforms to apply
            capture_uuid: UUID of the specific capture to transform.
        """
        # initialize the search_props field on the document
        # (presumes it doesn't exist)
        self.init_search_props(
            client=client,
            index_name=index_name,
            capture_uuid=capture_uuid,
        )

        for field, transform in field_transforms.items():
            try:
                try:
                    _response = client.update(
                        index=index_name,
                        id=capture_uuid,
                        body={
                            "script": {
                                "source": transform["source"],
                                "lang": transform["lang"],
                            },
                        },
                    )
                    if _response.get("result") != "updated":
                        self.stdout.write(
                            self.style.ERROR(
                                f"Failed to transform field '{field}': {_response!s}",
                            ),
                        )
                        continue
                    self.stdout.write(
                        f"Successfully TRANSFORMED field '{field}'",
                    )
                except (RequestError, OpensearchConnectionError) as e:
                    self.stdout.write(
                        self.style.ERROR(f"Error with direct update: {e!s}"),
                    )

            except (RequestError, OpensearchConnectionError) as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Error applying transform for field '{field}': {e!s}",
                    ),
                )

    def find_duplicate_captures(
        self,
        capture_type: CaptureType,
        index_name: str,
    ) -> dict[tuple[str], QuerySet[Capture]]:
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
        elif capture_type == CaptureType.DigitalRF:
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
        else:
            self.stdout.write(
                self.style.ERROR(f"Unknown capture type: {capture_type}"),
            )

        return duplicate_capture_groups

    def delete_duplicate_captures(
        self,
        client: OpenSearch,
        capture_type: CaptureType,
        index_name: str,
    ):
        """Delete duplicate captures from an index and database."""
        duplicate_capture_groups = self.find_duplicate_captures(
            capture_type=capture_type,
            index_name=index_name,
        )

        self.stdout.write(
            self.style.WARNING(
                f"Found {len(duplicate_capture_groups)} duplicate capture groups: "
                f"{duplicate_capture_groups}",
            ),
        )

        # if the dictionary is empty, return
        if not duplicate_capture_groups:
            self.stdout.write("No duplicate captures found")
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
                self.stdout.write(
                    self.style.ERROR(
                        "Capture group is empty, skipping deduplication...",
                    ),
                )
                continue
            if capture_group.count() <= 1:
                self.stdout.write(
                    self.style.WARNING(
                        "Capture group has 1 or fewer "
                        "captures, skipping deduplication...",
                    ),
                )
                continue
            duplicates_to_delete = capture_group.exclude(pk=oldest_capture.pk)

            match capture_type:
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
                    self.stdout.write(
                        self.style.ERROR(f"Unknown capture type: {capture_type}"),
                    )
                    return

            # delete all duplicates, keeping the oldest in each group
            for capture in duplicates_to_delete:
                self.delete_doc_by_capture_uuid(
                    client=client,
                    index_name=index_name,
                    capture_uuid=capture.uuid,
                )
                capture.delete()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Successfully DELETED duplicate capture '{capture.uuid}'",
                    ),
                )

    def delete_doc_by_capture_uuid(
        self,
        client: OpenSearch,
        index_name: str,
        capture_uuid: str,
    ) -> None:
        """Delete an OpenSearch document based on capture UUID."""
        try:
            # try to get the document
            client.get(index=index_name, id=capture_uuid)
        except NotFoundError:
            self.stdout.write(
                self.style.WARNING(
                    f"Document by capture UUID: '{capture_uuid}' not found",
                ),
            )
            return
        else:
            client.delete(index=index_name, id=capture_uuid)

    def reindex_single_capture(self, client: OpenSearch, capture: Capture) -> bool:
        """Reindex a capture."""
        self.stdout.write(
            self.style.WARNING(f"Reindexing capture manually: '{capture.uuid}'..."),
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
            transform_scripts = self.get_transform_scripts(capture.capture_type)
            if transform_scripts:
                self.apply_field_transforms(
                    client=client,
                    index_name=capture.index_name,
                    field_transforms=transform_scripts,
                    capture_uuid=str(capture.uuid),
                )
        except FileNotFoundError as e:
            self.stdout.write(
                self.style.ERROR(f"File not found for capture '{capture.uuid}': {e!s}"),
            )
            return False
        except (RequestError, OpensearchConnectionError) as e:
            self.stdout.write(
                self.style.ERROR(f"Error reindexing capture '{capture.uuid}': {e!s}"),
            )
            self.stdout.write(
                self.style.WARNING(f"Skipping capture '{capture.uuid}'..."),
            )
            return False
        else:
            return True

    def delete_index(self, client: OpenSearch, index_name: str) -> None:
        """Delete an index."""
        self.stdout.write(f"Deleting index '{index_name}'...")
        client.indices.delete(index=index_name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully DELETED index '{index_name}'",
            ),
        )

    def create_index(
        self,
        client: OpenSearch,
        index_name: str,
        index_config: dict[str, Any],
    ) -> None:
        """Create an index."""
        self.stdout.write(f"Creating index '{index_name}'...")
        client.indices.create(index=index_name, body=index_config)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully CREATED index '{index_name}'",
            ),
        )

    def clone_index(
        self,
        client: OpenSearch,
        source_index: str,
        target_index: str,
    ) -> None:
        """Clone an index."""

        def raise_target_exists() -> NoReturn:
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
                    index=source_index,
                    body={"settings": {"index.blocks.write": True}},
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
                    f"Successfully CLONED {source_index} to {target_index}",
                ),
            )

        except (RequestError, OpensearchConnectionError) as e:
            self.stdout.write(self.style.ERROR(f"Error cloning index: {e!s}"))
            raise
        finally:
            # Always re-enable writes on the source index
            client.indices.put_settings(
                index=source_index,
                body={"settings": {"index.blocks.write": None}},
            )

    def rollback_index(
        self,
        client: OpenSearch,
        index_name: str,
        backup_index_name: str,
    ):
        """Restore an index from a backup."""
        self.stdout.write(f"Restoring index '{index_name}' to its original state...")
        self.delete_index(client, index_name)
        self.clone_index(client, backup_index_name, index_name)
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully RESET {index_name} to its original form.",
            ),
        )

    def combine_scripts(self, transform_scripts: dict[str, dict[str, str]]) -> str:
        """Combine transform scripts into one source string."""
        return ";".join([script["source"] for script in transform_scripts.values()])

    # This function uses the reindex API to reindex documents with mapping changes.
    # It is kept here for reference, but is not used in the command.
    def reindex_with_mapping(
        self,
        client: OpenSearch,
        source_index: str,
        dest_index: str,
        capture_type: CaptureType,
    ):
        """Reindex documents with mapping changes."""
        try:
            # Get the transform scripts
            transform_scripts = self.get_transform_scripts(capture_type)

            # Perform reindex operation with combined transform scripts
            body = {
                "source": {"index": source_index},
                "dest": {"index": dest_index},
                "script": {
                    "source": self.combine_scripts(transform_scripts),
                    "lang": "painless",
                },
            }

            client.reindex(body=body)

            # Refresh destination index to make documents searchable
            client.indices.refresh(index=dest_index)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully REINDEXED from {source_index} to {dest_index}",
                ),
            )

        except (RequestError, OpensearchConnectionError, NotFoundError) as err:
            self.stdout.write(self.style.ERROR(f"Error during reindex: {err!s}"))
            if isinstance(err, RequestError) and err.info.get("failures"):
                failures = err.info.get("failures", [])
                self.stdout.write(
                    self.style.ERROR(
                        f"Some documents failed to reindex: {failures}",
                    ),
                )

                # prompt input to reindex the failed documents
                manual_reindex = (
                    input("Reindex failed documents manually? (y/N): ").lower() == "y"
                )
                self.stdout.write(
                    self.style.WARNING(f"Manual reindex: {manual_reindex}"),
                )
                if manual_reindex:
                    self.stdout.write(
                        self.style.WARNING("Reindexing failed documents manually..."),
                    )

                    # manually index the failed documents, skipping deleted captures
                    failed_captures = []
                    success_captures = []
                    for failure in failures:
                        capture = Capture.objects.get(uuid=failure["id"])
                        if not capture.is_deleted:
                            reindexed = self.reindex_single_capture(
                                capture=capture,
                                client=client,
                            )
                            if not reindexed:
                                failed_captures.append(capture)
                            else:
                                success_captures.append(capture)

                    if failed_captures:
                        self.stdout.write(
                            self.style.WARNING(
                                f"Failed to reindex {len(failed_captures)} "
                                f"captures: {failed_captures}",
                            ),
                        )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully REINDEXED {len(success_captures)} captures",
                        ),
                    )

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
                    f"Connection error while accessing '{index_name}': {e!s}",
                ),
            )
            return -1
        except AuthenticationException as e:
            self.stdout.write(
                self.style.ERROR(f"Authentication failed for '{index_name}': {e!s}"),
            )
            return -1
        except (RequestError, ValueError) as e:
            self.stdout.write(
                self.style.ERROR(
                    f"Unexpected error getting count for '{index_name}': {e!s}",
                ),
            )
            return -1

    def handle(self, *args, **options) -> None:
        """Execute the command."""
        response = input(
            "WARNING: This command is potentially destructive to existing "
            "Capture and OpenSearch index data and should be used with "
            "extreme caution.\n"
            "Are you sure you want to continue? (y/N): ",
        ).lower()
        if response != "y":
            self.stdout.write(self.style.WARNING("Command cancelled."))
            return

        client: OpenSearch = get_opensearch_client()
        capture_type = options["capture_type"]
        index_name = options["index_name"]

        try:
            # delete duplicate captures, including docs in the original index
            self.delete_duplicate_captures(
                client=client,
                capture_type=capture_type,
                index_name=index_name,
            )
        except Exception as err:
            self.stdout.write(
                self.style.ERROR(f"Error deleting duplicate captures: {err!s}"),
            )
            self.stdout.write(self.style.WARNING("Aborting command..."))
            raise

        # refresh the index
        client.indices.refresh(index=index_name)
        indices_mapping = self.get_indice_stats(client)
        self.offer_backup_restoration(
            client=client,
            index_name=index_name,
            maps=indices_mapping,
        )

        # use timezone-aware datetime without colon and lowercase (opensearch rules)
        _timestamp = datetime.now(UTC).strftime("%Y-%m-%d_t_%H-%M-%S")
        backup_index_name = f"{index_name}-backup-{_timestamp}"

        try:
            # get queryset of captures to reindex
            total_capture_count = Capture.objects.all().count()
            self.stdout.write(
                self.style.WARNING(
                    f"Total capture count: {total_capture_count}",
                ),
            )
            captures = Capture.objects.filter(
                capture_type=capture_type,
                index_name=index_name,
                is_deleted=False,
            )

            # log the number of captures to be reindexed
            total_captures = captures.count()
            self.stdout.write(
                self.style.WARNING(
                    f"Number of captures to reindex: {total_captures}",
                ),
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
                    self.style.ERROR(f"Skipping {index_name} due to count error"),
                )
                return

            # create backup index with same mapping
            try:
                self.clone_index(
                    client=client,
                    source_index=index_name,
                    target_index=backup_index_name,
                )
            except (RequestError, OpensearchConnectionError) as err:
                self.stdout.write(
                    self.style.ERROR(f"Failed to create backup index: {err!s}"),
                )
                return

            # verify backup index count matches original index count before continuing
            assert self.get_doc_count(client, backup_index_name) == original_count, (
                "Backup index count does not match original index count"
            )

            # delete original index and recreate it with new mapping
            self.delete_index(client=client, index_name=index_name)
            self.create_index(
                client=client,
                index_name=index_name,
                index_config=new_index_config,
            )

            client.indices.refresh(index=index_name)

            # reindex captures
            failed_captures = []
            successful_captures = []
            for capture in captures:
                capture_reindexed = self.reindex_single_capture(
                    capture=capture,
                    client=client,
                )
                if not capture_reindexed:
                    failed_captures.append(capture)
                else:
                    successful_captures.append(capture)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully REINDEXED {len(successful_captures)} "
                    f"captures / {total_captures}",
                ),
            )
            if failed_captures:
                self.stdout.write(
                    self.style.WARNING(
                        f"Failed to reindex {len(failed_captures)} / {total_captures} "
                        f"captures: {failed_captures}",
                    ),
                )

            client.indices.refresh(index=index_name)

            # now that all captures should be reindexed, delete
            # captures which linked files are still all missing
            self.delete_captures_with_only_missing_files(
                capture_type=capture_type,
                index_name=index_name,
            )

            is_reindex_successful, reasons = self.was_reindexing_successful(
                index_name=index_name,
                client=client,
            )
            if is_reindex_successful:
                new_count = self.get_doc_count(client=client, index_name=index_name)
                self.stdout.write(
                    self.style.SUCCESS(
                        "Successfully UPDATED index "
                        f"'{index_name}' with {new_count} docs",
                    ),
                )
            else:
                self.stdout.write(
                    self.style.ERROR(
                        f"Reindex verification failed for '{index_name}' with reasons:",
                    ),
                )
                for reason in reasons:
                    self.stdout.write(self.style.ERROR(f" - {reason}"))
                rollback_index = (
                    input(
                        "Would you like to reset the index "
                        "to its original form? (Y/n): ",
                    ).lower()
                    or "y"
                ) == "y"
                if rollback_index:
                    self.rollback_index(
                        client=client,
                        index_name=index_name,
                        backup_index_name=backup_index_name,
                    )
                else:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Keeping backup index {backup_index_name} "
                            "for manual verification.",
                        ),
                    )
                return

        except Exception as err:
            self.stdout.write(
                self.style.ERROR(f"Uncaught error during reindex: {err!s}"),
            )
            self.rollback_index(
                client=client,
                index_name=index_name,
                backup_index_name=backup_index_name,
            )
            raise

    def delete_captures_with_only_missing_files(
        self,
        capture_type: CaptureType,
        index_name: str,
    ) -> None:
        """Delete captures that have only missing files (should not exist).

        Run this after the reindex operation to make sure the database is clean.
        """
        self.stdout.write(
            self.style.WARNING(
                "Deleting captures with only missing files...",
            ),
        )
        self.stdout.write(
            self.style.WARNING(
                f"Capture cleanup for index '{index_name}'...",
            ),
        )
        captures = Capture.objects.filter(
            index_name=index_name,
            is_deleted=False,
            capture_type=capture_type,
        )
        if not captures:
            self.stdout.write("No captures to delete.")
            return

        marked_for_deletion: list[Capture] = []
        for capture in captures:
            all_files = cast("QuerySet[File]", capture.files.all())
            if (
                not all_files
                or all_files.count() == 0
                or all(file_obj.is_deleted for file_obj in all_files)
            ):
                marked_for_deletion.append(capture)
        if not marked_for_deletion:
            return

        self.stdout.write(
            self.style.WARNING(
                f"Deleting {len(marked_for_deletion)} captures "
                "that only have missing files linked to them.",
            ),
        )
        Capture.objects.filter(
            uuid__in=[capture.uuid for capture in marked_for_deletion],
        ).delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully deleted {len(marked_for_deletion)} captures.",
            ),
        )

    def was_reindexing_successful(
        self,
        index_name: str,
        client: OpenSearch,
    ) -> tuple[bool, list[str]]:
        """Checks the database is consistent with this index state.

        Args:
            index_name: Name of the index to check
            client:     OpenSearch client
        Returns:
            Whether the index is consistent with database
            A list of reasons it is not (if any)
        """
        client.indices.refresh(index=index_name)
        valid_captures = Capture.objects.filter(
            index_name=index_name,
            is_deleted=False,
        )
        capture_uuids_from_db = {
            str(uuid) for uuid in valid_captures.values_list("uuid", flat=True)
        }
        try:
            all_docs = client.search(
                index=index_name,
                size=MAX_OS_SIZE,  # pyright: ignore[reportCallIssue]
            )
        except RequestError as e:
            self.stdout.write(self.style.ERROR(f"Error searching index: {e!s}"))
            return False, []
        capture_uuids_from_opensearch = {
            str(doc["_id"]) for doc in all_docs["hits"]["hits"]
        }

        # make sure we're fetching all document IDs from this index
        if len(capture_uuids_from_opensearch) > 0.9 * MAX_OS_SIZE:
            self.stdout.write(
                f"Approaching OpenSearch search size limit of {MAX_OS_SIZE} docs:"
                " we'll need to write a lazy-loaded approach soon.",
            )
        assert self.get_doc_count(
            client=client,
            index_name=index_name,
        ) == len(capture_uuids_from_opensearch), (
            "Document count does not match the number of documents in the index: "
            f"{self.get_doc_count(client, index_name)} != "
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

    def get_indice_stats(self, client: OpenSearch) -> dict[str, dict[str, Any]]:
        """Shows number of docs across stats indices and returns their mapping."""
        maps = client.indices.get_mapping("*")
        for index_name in maps:
            doc_count = self.get_doc_count(client=client, index_name=index_name)
            self.stdout.write(
                self.style.WARNING(
                    f"{index_name:>60} index: {doc_count:>6} documents",
                ),
            )

        return maps

    def restore_index_from_backup(
        self,
        client: OpenSearch,
        index_name: str,
        backup_index_name: str,
    ) -> None:
        """Restores an index from one of its backups."""
        self.stdout.write(
            f"Restoring index '{index_name}' from backup '{backup_index_name}'...",
        )
        self.delete_index(client=client, index_name=index_name)
        self.clone_index(
            client=client,
            source_index=backup_index_name,
            target_index=index_name,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully RESTORED {index_name} from {backup_index_name}",
            ),
        )
        client.indices.refresh(index=index_name)

    def offer_backup_restoration(
        self,
        client: OpenSearch,
        index_name: str,
        maps: dict[str, dict[str, Any]],
    ) -> None:
        """Offers to restore a backed up index if found to have more documents."""
        target_index_doc_count = self.get_doc_count(
            client=client,
            index_name=index_name,
        )
        backups_of_target_index = [
            name for name in maps if name.startswith(f"{index_name}-backup-")
        ]
        if not backups_of_target_index:
            # no backups found
            return

        backup_doc_counts = {
            name: self.get_doc_count(client=client, index_name=name)
            for name in backups_of_target_index
        }
        max_backup_name, max_backup_count = max(
            backup_doc_counts.items(),
            key=lambda item: item[1],
        )

        if max_backup_count <= target_index_doc_count:
            # no good restoration candidate
            return

        self.stdout.write(
            self.style.WARNING(
                f"WARNING: '{index_name}' has a backup '{max_backup_name}' with more "
                f"documents than it ({max_backup_count} > {target_index_doc_count})",
            ),
        )
        response = (
            input(
                f"Would you like to restore '{index_name}' "
                f"from its backup '{max_backup_name}' before continuing? (y/N): ",
            )
            .strip()
            .lower()
        )

        if response == "y":
            self.restore_index_from_backup(
                client=client,
                index_name=index_name,
                backup_index_name=max_backup_name,
            )
