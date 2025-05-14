"""Django management command to initialize OpenSearch indices."""

from typing import Any

from django.core.management.base import BaseCommand
from loguru import logger as log
from opensearchpy import OpenSearch
from opensearchpy.exceptions import RequestError

from sds_gateway.api_methods.models import CaptureType
from sds_gateway.api_methods.utils.metadata_schemas import get_mapping_by_capture_type
from sds_gateway.api_methods.utils.opensearch_client import get_opensearch_client


class Command(BaseCommand):
    """Initialize OpenSearch indices for different capture types."""

    help = "Initialize or update OpenSearch indices with mappings"
    client: OpenSearch

    def handle(self, *args, **options) -> None:
        """Execute the command."""
        self.client: OpenSearch = get_opensearch_client()

        # Loop through capture types to create/update indices
        for capture_type in CaptureType:
            # TODO: add sigmf capture props to metadata schemas
            if capture_type == CaptureType.SigMF:
                log.debug(
                    "Index init skipping SigMF capture type: "
                    "remove this check when SigMF mapping is added",
                )
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
                self.init_index(
                    index_name=index_name,
                    index_config=index_config,
                )
                self.make_index_writeable(
                    index_name=index_name,
                )
            except Exception as e:
                log.error(
                    f"Failed to initialize/update index '{index_name}': {format(e)}",
                )
                raise

    def init_index(
        self,
        *,
        index_name: str,
        index_config: dict[str, Any],
    ) -> None:
        if not self.client.indices.exists(index=index_name):
            # create new index with mapping
            log.info(f"Creating index '{index_name}'...")
            self.client.indices.create(
                index=index_name,
                body=index_config,
            )
            log.success(f"Created index '{index_name}'")
            return

        current_mapping = self.client.indices.get_mapping(index=index_name)
        current_properties = current_mapping[index_name]["mappings"].get(
            "properties",
            {},
        )
        new_properties = index_config["mappings"]["properties"]

        # only update if mappings are different
        if current_properties == new_properties:
            log.success(f"No mapping updates needed for '{index_name}'")
            return

        log.info(f"Updating mapping for index '{index_name}'...")
        try:
            self.client.indices.put_mapping(
                index=index_name,
                body=index_config["mappings"],
            )
            log.success(f"Updated mapping for '{index_name}'")
        except RequestError as e:
            if "mapper_parsing_exception" not in str(e):
                raise
            log.warning(
                "Cannot update mapping for "
                f"'{index_name}'. Some fields are "
                "incompatible with existing mapping. "
                f"Error: {format(e)}",
            )

    def make_index_writeable(
        self,
        *,
        index_name: str,
    ) -> None:
        # make index writeable
        log.info(f"Making index '{index_name}' writeable...")
        self.client.indices.put_settings(
            index=index_name,
            body={"settings": {"index.blocks.write": False}},
        )
        # get settings to assert
        settings = self.client.indices.get_settings(index=index_name)
        index_settings = settings[index_name]["settings"]["index"]
        write_block = index_settings.get("blocks", {}).get("write", None)
        valid_write_states = [None, "false", False]
        assert write_block in valid_write_states, (
            f"Index '{index_name}' is not writeable. Current "
            f"state for write block: {write_block} {type(write_block)}"
        )
        log.success(f"Made index '{index_name}' writeable")
