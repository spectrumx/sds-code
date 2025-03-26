"""Django management command to initialize OpenSearch indices."""

from typing import TYPE_CHECKING

from django.core.management.base import BaseCommand
from opensearchpy.exceptions import RequestError

if TYPE_CHECKING:
    from opensearchpy import OpenSearch

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


class Command(BaseCommand):
    """Initialize OpenSearch indices for different capture types."""

    help = "Initialize or update OpenSearch indices with mappings"

    def handle(self, *args, **options):
        """Execute the command."""
        client: OpenSearch = get_opensearch_client()

        # Loop through capture types to create/update indices
        for capture_type in CaptureType:
            # remove sigmf capture type for now
            # TODO: add sigmf capture props to metadata schemas
            if capture_type == CaptureType.SigMF:
                continue

            index_name = f"captures-{capture_type.value}"
            index_config = {
                "mappings": get_mapping_by_capture_type(capture_type),
                "settings": {
                    "index": {
                        "number_of_shards": 1,
                        "number_of_replicas": 1,
                    },
                },
            }

            try:
                # Check if index exists
                if not client.indices.exists(index=index_name):
                    # Create new index with mapping
                    self.stdout.write(f"Creating index '{index_name}'...")
                    client.indices.create(
                        index=index_name,
                        body=index_config,
                    )
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"Successfully created index '{index_name}'",
                        ),
                    )
                else:
                    # Get current mapping
                    current_mapping = client.indices.get_mapping(index=index_name)
                    current_properties = current_mapping[index_name]["mappings"].get(
                        "properties",
                        {},
                    )
                    new_properties = index_config["mappings"]["properties"]

                    # Only update if mappings are different
                    if current_properties != new_properties:
                        self.stdout.write(
                            f"Updating mapping for index '{index_name}'...",
                        )
                        try:
                            client.indices.put_mapping(
                                index=index_name,
                                body=index_config["mappings"],
                            )
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Successfully updated mapping for '{index_name}'",
                                ),
                            )
                        except RequestError as e:
                            if "mapper_parsing_exception" in str(e):
                                self.stdout.write(
                                    self.style.WARNING(
                                        "Cannot update mapping for "
                                        f"'{index_name}'. Some fields are "
                                        "incompatible with existing mapping. "
                                        f"Error: {format(e)}",
                                    ),
                                )
                            else:
                                raise
                    else:
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"No mapping updates needed for '{index_name}'",
                            ),
                        )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed to initialize/update index '{index_name}': "
                        f"{format(e)}",
                    ),
                )
                raise
