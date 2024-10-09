# SpectrumX Data System (SDS) SDK

![PyPI - Version](https://img.shields.io/pypi/v/spectrumx)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/spectrumx)
![Pepy Total Downloads](https://img.shields.io/pepy/dt/spectrumx)
[![Action | Upload Python Package](https://github.com/spectrumx/sds-code/actions/workflows/python-publish.yaml/badge.svg)](https://github.com/spectrumx/sds-code/actions/workflows/python-publish.yaml)

The SDK is the primary form that clients interact with SDS: either directly by installing the Python package from PyPI, or indirectly by using the SDS Web UI or the Visualization Component.

+ [SpectrumX Data System (SDS) SDK](#spectrumx-data-system-sds-sdk)
    + [Usage Guide](#usage-guide)
        + [Installation](#installation)
        + [Usage](#usage)
        + [Asset types](#asset-types)
        + [SDK Methods](#sdk-methods)
        + [Supported Python Versions](#supported-python-versions)
    + [SDK Development](#sdk-development)
        + [Design Goals](#design-goals)
        + [Testing](#testing)

## Usage Guide

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

    # fetch a dataset by its ID
    dataset = Dataset.get(sds, dataset_id="dataset-id")
    ```

### Asset types

The SDK provides classes for the following asset types:

| Asset Type   | Description                                                                                                                                                                       |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `File`       | Represents a file that was uploaded to SDS. It may be one of a variety of formats allowed. It is the smallest addressable unit in SDS.                                            |
| `Directory`  | A directory is a unique attribute of a file in the form of a path and does not match how files are stored on the server. It is merely used to arrange files on the client side.\* |
| `Capture`    | Special type of file that refers to an RF capture and is indexed and searchable. Uses the same ID as the file it represents.                                                      |
| `Dataset`    | Logical grouping of files in the SDS with metadata and a unique identifier. Ideal for sharing collections of files.                                                               |
| `Experiment` | Logical grouping of zero or more datasets, captures, and files. It is a logical grouping of datasets and captures.                                                                |

+ \* There are many benefits of treating directories as attributes (assume `<path>` equals to `<directory>/<filename>`):
    1. **Separation of concerns:** SDS and clients have different goals when it comes to file organization. Directories as attributes let users organize their files in ways that make sense to them without affecting SDS.
    2. **Update performance:** when users change their file trees and tell the SDK "re-upload" them, all the SDK has to do is detect the files moved, then issue the proper commands for the server to update those attributes. This prevents same content re-upload and updating database attributes is also faster than moving files.
    3. **Access performance:** querying rows from a database is faster than traversing a file system when listing files and directories. Directory attributes can be sorted, cached, indexed, and filtered efficiently. Storing these files in a file system _as well as_ creating their database entries would lead to multiple sources of truth and potential inconsistencies over time.
    4. **Reliability:** in case of interruption, a move operation is harder to recover from than an attribute update; the latter is also easier to model as an atomic database transaction and give immediate feedback to the user.
    5. **No empty directories:** a path (and its directory) only exists if there is a file "in" it.
    6. **Orthogonal soft deletions:** the directory attribute can be preserved in the case of deletions, making "un-deletions" faster and more reliable.
    7. **File versioning for free:** if a new file has the same path as an existing one, the server will store both by their checksums and the SDK can indicate there are multiple versions available when listing by path.
    8. **File duplication:** if a file the server already has is re-uploaded, the SDK can avoid the extraneous data transfer and an additional "file" row can be created pointing to an already existing file on the server's disk.

### SDK Methods

| Method             | Asset                             | Action Group | Description                                                        |
| ------------------ | --------------------------------- | ------------ | ------------------------------------------------------------------ |
| `sds.authenticate` | Client                            | -            | Authenticates the client with SDS.                                 |
| `sds.files`        | File                              | Listing      | Returns an iterator for files available to the current user.       |
| `sds.datasets`     | Dataset                           | Listing      | Returns an iterator for datasets available to the current user.    |
| `sds.captures`     | Capture                           | Listing      | Returns an iterator for captures available to the current user.    |
| `sds.experiments`  | Experiment                        | Listing      | Returns an iterator for experiments available to the current user. |
| `sds.upload`       | Capture, Dataset, File, Directory | Create       | Uploads the asset to SDS.                                          |
| `sds.download`     | Capture, Dataset, File, Directory | Read         | Downloads the asset from SDS.                                      |
| `sds.search`       | Capture, Dataset, Directory       | Listing      | Searches for assets based on filters.                              |
| `<asset>.update`   | Capture, Dataset, File, Directory | Update       | Updates the asset's metadata.                                      |
| `<asset>.delete`   | Capture, Dataset, File, Directory | Delete       | Marks the asset for deletion.                                      |

### Supported Python Versions

Maintaining older Python versions has a cost. The SpectrumX SDK aims to support the 2 most recent stable versions of Python at any given time, dropping support to Python versions 3 years after their initial release, in accordance to the [Scientific Python Ecosystem Coordination recommendation](https://scientific-python.org/specs/spec-0000/). With our first release being after Python 3.13 stable is out, the plan is to support Python versions 3.13 and 3.12 at launch. This may be revisited as the project matures.

## SDK Development

### Design Goals

For a stable "v1" release and in no particular order:

1. **Unified APIs for File Operations**

    Implement a cohesive and simplified set of methods for common file operations such as upload, download, delete, list, and move.

2. **Object-Oriented Approach**

    The SDK handles files and directories as objects, making their properties (metadata) and methods (actions) easily available and discoverable in text editors and IDEs.

3. **Multipart Down/Uploads and Fault Tolerance**

    Implement support for multipart transfers, especially useful for large files. Uploads and downloads should be resumable if possible. Uploads and downloads should be fault-tolerant, meaning they are to be made idempotent and atomic at the smallest unit of operation (file contents + metadata). Integration tests should cover these scenarios.

4. **Access Control and Authentication**

    Token-based authentication and authorization will be used for secure access to SDS assets. In the stable release of the SDK, all requests must use TLS (HTTPS enforced). Assets are only editable by their owners or SDS administrators. Enforcement of these access control policies will be done at the server level (SDS Gateway).

5. **Caching and Optimization**

    Requests that return iterators should be paginated and/or lazy-loaded (e.g. with generators). Caching should be used to reduce the number of requests to the server and reduce bandwidth usage. The SDK must offer a global flag to disable all SDK caching (e.g. for tests, debugging, or even user control). The SDK must automatically skip operations that were already performed (when possible to tell) _and_ are idempotent (e.g. re-downloading or re-uploading the same file, recreating the same dataset). As with caching, the user should be able to manually disable this SDK's auto-skip optimization with an optional flag passed to the method e.g. `force_download=True`.

6. **Scalability and Concurrency**

    The SDK should be able to handle multiple network requests concurrently, especially for large file transfers. This can be achieved with a connection pool and `asyncio`.

    **Impl. idea:** to prevent larger file transfers taking all connections and improve the instant file throughput, we could run two kinds of pools concurrently: one long (for the larger files) and one short (for the smaller ones).

    **Note on concurrent writes / warning to users:** do not run concurrent scripts and/or multiple processes that use SDS SDK clients for writes. It is out of the scope for the SDK to protect data from concurrent writes from multiple processes that use the SDK connected to the same host (as in running the same SDK script more than once and concurrently). In that case, the system is likely to enter a "last-writer-wins" conflict resolution, which may incur loss of data. Since writes are limited to the data owner, this potential data loss is limited to a single user running instances writing to the same locations. Preventing this would require the implementation of ACID-like transactions for resource locking at the server side, thus increasing development time.

7. **Error handling and user feedback**

    The SDK should handle warnings and errors from the server in a user-friendly way. Warnings deliver information that might require user action soon, while errors require immediate attention. Success messages, when enabled, should be informative and concise. On exceptions, the SDK should raise exceptions related to the operation that failed, for example, if a dataset metadata update failed, prefer something like `DatasetUpdateError` over a generic `HTTPError` with code status code 400.

8. **Data content and space management**

    User feedback should be provided when the user is about to exceed their storage quota. The SDK should also provide a way to check the user's storage usage and quota. The SDK should skip forbidden file extensions and MIME types automatically and warn the user about them. Both quota limits and content types are enforced at the server level, the SDK merely provides a more user-friendly and contextual interface.

### Testing

```bash
uv sync --dev

# simple tests execution
uv run pytest -v

# running a specific test
uv run pytest -v tests/test_usage.py::test_authentication_200_succeeds

# running similar tests (substring match)
uv run pytest -v -k test_authentication

# verbose with colored log messages
uv run pytest -vvv --show-capture=stdout -o log_cli=true --log-cli-level=DEBUG --capture=no
```
