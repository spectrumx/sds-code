"""Django management command to initialize OpenSearch indices."""

from django.core.management.base import BaseCommand
from opensearchpy import OpenSearch

from sds_gateway.api_methods.helpers.index_handling import create_index
from sds_gateway.api_methods.models import Capture
from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client
from sds_gateway.api_methods.views.capture_endpoints import CaptureViewSet


class Command(BaseCommand):
    """Initialize OpenSearch indices for different capture types."""

    help = "Initialize or update OpenSearch indices with mappings"

    def reindex_captures(
        self, client: OpenSearch, index_name: str, capture_type: CaptureType
    ):
        """Reindex captures for a given capture type."""
        captures = Capture.objects.filter(capture_type=capture_type)
        for capture in captures:
            capture_viewset = CaptureViewSet()
            capture_viewset.ingest_capture(
                capture=capture,
                drf_channel=capture.channel,
                rh_scan_group=capture.scan_group,
                requester=capture.owner,
                top_level_dir=capture.top_level_dir,
                connect_files=False,
            )

    def handle(self, *args, **options):
        """Execute the command."""
        client: OpenSearch = get_opensearch_client()

        # Loop through capture types to create/update indices
        for capture_type in CaptureType:
            # remove sigmf capture type for now
            # TODO: add sigmf capture props to metadata schemas
            if capture_type == CaptureType.SigMF:
                continue

            index_name = f"captures-{capture_type}"

            # delete index
            client.indices.delete(index=index_name)

            # create index
            create_index(client, index_name, capture_type)

            # reindex captures
            self.reindex_captures(client, index_name, capture_type)
