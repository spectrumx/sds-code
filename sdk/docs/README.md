# SpectrumX Data System | SDK

![PyPI - Version](https://img.shields.io/pypi/v/spectrumx)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/spectrumx)
![Pepy Total Downloads](https://img.shields.io/pepy/dt/spectrumx)

+ [SpectrumX Data System | SDK](#spectrumx-data-system--sdk)
    + [Installation](#installation)
    + [Basic Usage](#basic-usage)
    + [Error Handling](#error-handling)
    + [Full example (not implemented)](#full-example-not-implemented)

The Spectrum Data System (SDS) SDK is a Python package that provides a simple interface for interacting with the SDS Gateway. The SDK is designed to be easy to use and to provide a high-level interface for common tasks, such as uploading and downloading files, searching for files, and managing RF datasets.

> [!NOTE]
>
> **SDS is not meant for personal files or as a backup tool.** Files may be rejected by the Gateway when uploaded, or deleted without warning. Do not upload sensitive, personally identifiable, confidential information, or any file that you do not have permission to share. Do not upload binary executables.
>
> If you own data in `https://sds.crc.nd.edu` that needs to be permanently deleted, please reach out to the team, as SDS may retain uploaded data for a period of time after deletion.

## Installation

```bash
uv add spectrumx
# or one of:
#   pip install spectrumx
#   conda install spectrumx
#   ...
```

## Basic Usage

1. In a file named `.env`, enter the `secret_token` provided to you:

    ```ini
    SDS_SECRET_TOKEN=your-secret-token-no-quotes
    ```

    OR set the environment variable `SDS_SECRET_TOKEN` to your secret token:

    ```bash
    # the env var takes precedence over the .env file
    export SDS_SECRET_TOKEN=your-secret-token
    ```

2. Then, in your Python script or Jupyter notebook. [See `examples/basic-usage.py`](./examples/basic-usage.py) for the full script.:

    ```python
    from spectrumx import Client
    from pathlib import Path

    # NOTE: the SDS client-server interaction is stateless, so it is
    #   not recommended to have multiple clients writing to the same
    #   locations simultaneously, as they may overrule each other
    #   and cause loss of data.
    sds = Client(
        host="sds.crc.nd.edu",
        # env_file=Path(".env"),  # default
        # env_config={"SDS_SECRET_TOKEN": "my-custom-token"},  # overrides
    )

    # when in dry-run, no changes are made to the SDS or the local filesystem
    sds.dry_run = True

    # authenticate using either the token from
    # the .env file or in the config passed in
    sds.authenticate()

    # upload all files in a directory to the SDS
    reference_name: str = "my_spectrum_capture"
    local_dir: Path = Path(reference_name)
    sds.upload(
        local_dir,  # may be a single file or a directory
        sds_path=reference_name,  # files will be created under this virtual directory
        verbose=True,  # shows a progress bar (default)
    )

    # download all files in a directory from the SDS
    local_downloads: Path = Path("sds-downloads")
    sds.download(
        sds_path=reference_name,  # files will be downloaded from this virtual directory
        to=local_downloads,  # download to this location; will be created if needed
        overwrite=False,  # do not overwrite local existing files (default)
        verbose=True,  # shows a progress bar (default)
    )
    ```

## Error Handling

The SDK provides context-aware exceptions that can be caught and handled in your code.

Authentication:

```py
from spectrumx import AuthError, NetworkError

# ...
try:
    sds.authenticate()
except NetworkError as err:
    print(f"Failed to connect to the SDS: {err}")
    # check your host= parameter and network connection
    # if you're hosting the SDS Gateway, make sure it is accessible
except AuthError as err:
    print(f"Failed to authenticate: {err}")
    # TODO: take action
```

Retries and `SDSError`s:

```py
from time import sleep
from spectrumx import NetworkError, SDSError, ServiceError

# ...
is_success = False
retries_left: int = 5
while not is_success and retries_left > 0:
    try:
        retries_left -= 1
        # the sds.upload will restart a partial file transfer from zero,
        # but it won't re-upload already finished files.
        sds.upload(
            local_dir,
            sds_root=reference_name,
            verbose=True,
        )
        is_success = True
    except (NetworkError, ServiceError) as err:
        # NetworkError refers to connection issues between client and SDS Gateway
        # ServiceError refers to issues with the SDS Gateway itself (e.g. HTTP 500 errors)
        # sleep longer with each retry, at least 5s, up to 5min
        sleep_time = max(5, 5 / (retries_left ** 2) * 60)
        print(f"Failed to reach the gateway; sleeping {sleep_time}s")
        print(f"Error: {err}")
        if retries_left > 0:
            sleep(sleep_time)
        continue
    except SDSError as err:
        print(f"Another SDS error occurred: {err}")
        # other errors might include e.g. OSError
        #   if listed files cannot be found.
        # TODO: take action or break
        break
```

## Full example (not implemented)

> [!WARNING]
>
> The basic functionality in the example below may not be implemented in early
> versions of the SDK and is subject to change before a stable v1.0 release.

```python
from spectrumx import Client
from spectrumx.models import Capture, Dataset
from pathlib import Path

sds = Client(
    host="sds.crc.nd.edu"
)

# authenticate using either the token from
# the .env file or in the config passed in
sds.authenticate()

# get list of datasets available
print("Dataset name | Dataset ID")
for dataset in sds.datasets():
    print(f"{dataset.name} | {dataset.id}")

# download a dataset to a local directory
local_downloads = Path("datasets")
most_recent_dataset: Dataset = sds.datasets()[0]
most_recent_dataset.download_assets(
    to=local_downloads, # download to this location + dataset_name
    overwrite=False,    # do not overwrite local files (default)
    verbose=True,       # shows a progress bar (default)
)

# search for capture files between two frequencies and dates
# a "capture" represents a file in the SDS in a known format, such
# as a Digital RF archive or SigMF file.
start_time = datetime.datetime(2024, 1, 1, 0, 0, 0)
end_time = datetime.datetime(2024, 1, 2, 0, 0, 0)
captures = sds.search(
    asset_type=Capture,
    center_freq_range=(3e9, 5e9), # between 3 and 5 GHz
    capture_time_range=(start_time, end_time),
    # additional arguments work as "and" filters
)
for capture in captures:
    print(capture.id)
    capture.download(
        to=local_downloads / "search_results",
        overwrite=False,
        verbose=True,
    )

# fetch a dataset by its ID
dataset = Dataset.get(sds, dataset_id="dataset-id")
```
