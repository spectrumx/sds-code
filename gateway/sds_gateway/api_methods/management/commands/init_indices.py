"""Django management command to initialize OpenSearch indices."""

from django.core.management.base import BaseCommand
from opensearchpy import exceptions as os_exceptions

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import (
    capture_index_mapping_by_type as md_props_by_type,
)
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


class Command(BaseCommand):
    """Initialize OpenSearch indices for different capture types."""

    help = "Initialize OpenSearch indices for different capture types"

    def handle(self, *args, **options):
        """Execute the command."""
        client = get_opensearch_client()

        for capture_type in CaptureType:
            # remove sigmf capture type for now
            # TODO: add sigmf capture props to metadata schemas
            if capture_type == CaptureType.SigMF:
                continue

            index_name = f"captures-{capture_type.value}"
            try:
                # Define the index settings and mappings
                index_body = {
                    "settings": {
                        "number_of_shards": 1,
                        "number_of_replicas": 0,
                    },
                    "mappings": {
                        "properties": {
                            "channel": {"type": "keyword"},
                            "capture_type": {"type": "keyword"},
                            "created_at": {"type": "date"},
                            "capture_props": {
                                "type": "nested",
                                "properties": md_props_by_type[capture_type],
                            },
                        },
                    },
                }
                client.indices.create(index=index_name, body=index_body)
                self.stdout.write(
                    self.style.SUCCESS(f"Index '{index_name}' created successfully."),
                )
            except os_exceptions.RequestError as e:
                if "resource_already_exists_exception" in str(e):
                    self.stdout.write(
                        self.style.WARNING(
                            f"Index '{index_name}' already exists, skipping.",
                        ),
                    )
                else:
                    self.stdout.write(
                        self.style.ERROR(f"Error creating index '{index_name}': {e}"),
                    )
