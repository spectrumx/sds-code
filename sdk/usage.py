#!/usr/bin/env python
"""Usage examples for the SpectrumX Data System SDK.

Work in progress - this script is for reference only and it's not functional yet.
"""

import datetime
from pathlib import Path

from loguru import logger as log
from spectrumx import Client
from spectrumx.models import Capture
from spectrumx.models import Dataset


def main() -> None:
    """Usage script entrypoint"""
    log.info("Usage examples for the SpectrumX Data System SDK")

    sds = Client(host="sds.crc.nd.edu")

    # authenticate using either the token from
    # the .env file or the env variable
    sds.authenticate()

    # get list of datasets available
    log.info("Dataset name | Dataset ID")
    for dataset in sds.datasets():
        log.info(f"{dataset.name} | {dataset.id}")

    # download a dataset to a local directory
    local_downloads = Path("datasets")
    most_recent_dataset: Dataset = next(sds.datasets())
    most_recent_dataset.download_assets(
        to=local_downloads,  # download to this location + dataset_name
        overwrite=False,  # do not overwrite existing files (default)
        verbose=True,  # shows a progress bar (default)
    )

    # search for capture files between two frequencies and dates
    # a "capture" represents a file in the SDS in a known format, such
    # as a Digital RF archive or SigMF file.
    start_time = datetime.datetime(2024, 1, 1, 0, 0, 0, tzinfo=datetime.UTC)
    end_time = datetime.datetime(2024, 1, 2, 0, 0, 0, tzinfo=datetime.UTC)
    captures = sds.search(
        asset_type=Capture,
        center_freq_range=(3e9, 5e9),  # between 3 and 5 GHz
        capture_time_range=(start_time, end_time),
        # additional arguments work as "and" filters
    )
    for capture in captures:
        log.info(capture.id)
        capture.download(
            to=local_downloads / "search_results",
            overwrite=False,
            verbose=True,
        )

    # fetch a dataset by its ID
    dataset = Dataset.get(sds, dataset_id="dataset-id")


if __name__ == "__main__":
    main()
