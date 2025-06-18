import logging

from sds_gateway.api_methods.models import Dataset
from sds_gateway.api_methods.models import File

logger = logging.getLogger(__name__)


def get_dataset_files(dataset: Dataset) -> list[File]:
    """
    Get all files associated with a dataset, including files from linked captures.

    Args:
        dataset: Dataset model instance

    Returns:
        List[File]: List of all files associated with the dataset
    """
    files: set[File] = set()

    # Get files directly associated with the dataset
    dataset_files = dataset.files.filter(is_deleted=False)
    files.update(dataset_files)
    logger.info(
        "Found %d files directly associated with dataset %s",
        dataset_files.count(),
        dataset.uuid,
    )

    # Get files from captures linked to the dataset
    dataset_captures = dataset.captures.filter(is_deleted=False)
    for capture in dataset_captures:
        capture_files = capture.files.filter(is_deleted=False)
        files.update(capture_files)
        logger.info(
            "Found %d files from capture %s", capture_files.count(), capture.uuid
        )

    # Convert set to list and sort by creation date
    file_list = list(files)
    file_list.sort(key=lambda x: x.created_at)

    logger.info("Total files found for dataset %s: %d", dataset.uuid, len(file_list))
    return file_list
