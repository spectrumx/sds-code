"""Usage example of the SpectrumX client."""

# Disabling QA checks for this file until the client is implemented
# type: ignore
# pyright: reportAttributeAccessIssue=false, reportMissingImports=false
# pylint: disable=import-error

import datetime
from pathlib import Path

from spectrumx import Client
from spectrumx.models import Capture, Dataset

sds = Client(host="sds.crc.nd.edu")

# authenticate using either the token from
# the .env file or the env variable
sds.authenticate()

# get list of datasets available
print("Dataset name | Dataset ID")
for dataset in sds.datasets():
    print(f"{dataset.name} | {dataset.id}")

# download a dataset to a local directory
local_downloads = Path("datasets")
most_recent_dataset: Dataset = sds.datasets()[0]
most_recent_dataset.download_assets(
    to=local_downloads,  # download to this location + dataset_name
    overwrite=False,  # do not overwrite existing files (default)
    verbose=True,  # shows a progress bar (default)
)

# search for capture files between two frequencies and dates
# a "capture" represents a file in SDS with a known format, such
# as a Digital RF archive or SigMF file.
start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
end_time = datetime.datetime(2024, 1, 2, 0, 0, 0)
captures = sds.search(
    asset_type=Capture,
    center_freq_range=(3e9, 5e9),  # between 3 and 5 GHz
    capture_time_range=(start_time, end_time),
    # additional arguments work as "and" filters
)

# download the capture files to a local directory
for capture in captures:
    print(capture.id)
    capture.download(
        to=local_downloads / "search_results",
        overwrite=False,
        verbose=True,
    )
