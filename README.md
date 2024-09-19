# SpectrumX Data System | SDK and Gateway

**Code for the SpectrumX Data System (SDS) SDK and Gateway.**

The SDK (Software Dev Kit) here is a reference implementation in Python to interact with the API exposed by the Gateway.

The SDK is the primary form that clients interact with SDS: either directly by installing the Python package from PyPI, or indirectly by using the SDS Web UI or the Visualization Component.

Clients may use the SDK to authenticate, to push and pull data from SDS, and to discover assets stored in the system. In general, basic CRUD operations on SDS entities are to be eventually supported by this system. At a high level:

```txt
+-----------+          +--------+            +---------+            +---------------+
|           | 1. Auth  |        | 2. API     |         | 3. Data    |               |
|           |<-------->|        | Requests+  |         | Requests+  |               |
|  Client   |          |  SDK   | responses  | Gateway | responses  | SDS Data Store|
|           |          |        |            |         |            |               |
|           |<-------->|        |<---------->|         |<---------->|               |
|           | 4. User  |        |            |         |            |               |
|           |    Reqs. |        |            |         |            |               |
|           |          |        |            |         |            |               |
+-----------+          +--------+            +---------+            +---------------+
```

## SDK

### Installation

```bash
pip install spectrumx-sdk
# uv add spectrumx-sdk
# conda install spectrumx-sdk
```

### Usage

1. In a file named `.env`, enter the `secret_token` provided to you:

    ```ini
    SDS_SECRET_TOKEN=your-secret-token-no-quotes
    ```

    OR set the environment variable `SDS_SECRET_TOKEN` to your secret token.

    ```bash
    # the env var takes precedence over the .env file
    export SDS_SECRET=your-secret-token
    ```

2. Then, in your Python script or Jupyter notebook:

    ```python
    from spectrumx_sdk import Client
    from spectrumx_sdk.models import Capture, Dataset
    from pathlib import Path

    sds = Client(
        host="sds.crc.nd.edu"
    )

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
        to=local_downloads, # download to this location + dataset_name
        overwrite=False,    # do not overwrite existing files (default)
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
    ```

### Supported Python Versions

Maintaining older Python versions has a cost. The SpectrumX SDK aims to support the 2 most recent stable versions of Python at any given time, dropping support to Python versions 3 years after their initial release, in accordance to the [Scientific Python Ecosystem Coordination recommendation](https://scientific-python.org/specs/spec-0000/). With our first release being after Python 3.13 stable is out, the plan is to support Python versions 3.13 and 3.12 at launch. This may be revisited as the project matures.
