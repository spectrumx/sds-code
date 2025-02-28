# SpectrumX Data System | SDK

[![PyPI - Version](https://img.shields.io/pypi/v/spectrumx)](https://pypi.org/project/spectrumx/)
[![PyPI - Python Versions](https://img.shields.io/pypi/pyversions/spectrumx)](https://pypi.org/project/spectrumx/)
[![Pepy Total Downloads](https://img.shields.io/pepy/dt/spectrumx)](https://pypi.org/project/spectrumx/)

+ [SpectrumX Data System | SDK](#spectrumx-data-system--sdk)
    + [Installation](#installation)
    + [Basic Usage](#basic-usage)
    + [Error Handling](#error-handling)

The SpectrumX Data System (SDS) SDK is a Python package that provides a simple interface for interacting with the SDS Gateway. The SDK is designed to be easy to use and to provide a high-level interface for common tasks, such as uploading and downloading files, searching for files, and managing RF datasets.

> [!NOTE]
>
> **SDS is not meant for personal files or as a backup tool.** Files may be rejected by the Gateway when uploaded, or deleted without warning. All uploaded files have an expiration date. Do not upload sensitive, personally identifiable, confidential information, or any file that you do not have permission to share. Do not upload binary executables.
>
> If you own data in `https://sds.crc.nd.edu` that needs to be permanently deleted, please reach out to the team at `crc-sds-list [·at·] nd.edu`, as SDS may retain uploaded data for a period of time after deletion.

## Installation

```bash
uv add spectrumx

# or one of:
#   poetry add spectrumx
#   pip install spectrumx
#   conda install spectrumx
#   ...
```

> [!NOTE]
> When not using `uv`, make sure you are using Python 3.12 or higher (`python --version`).

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

2. Then, in your Python script or Jupyter notebook ([See more usage examples](./tests/e2e_examples/check_build_acceptance.py) in `./tests/e2e_examples/` for the full script):

    ```python
    from pathlib import Path
    from random import randint, random
    from spectrums.client import Client

    # Example of files upload, listing, and download from SDS.

    # NOTE: the SDS client-server interaction is stateless, so it is
    #   not recommended to have multiple clients writing to the same
    #   locations simultaneously, as they may overrule each other
    #   and cause loss of data.
    sds = Client(
        host="sds.crc.nd.edu",
        # env_file=Path(".env"),  # default
        # env_config={"SDS_SECRET_TOKEN": "my-custom-token"},  # overrides
    )

    # when in dry-run (default), no changes are made to the SDS or the local filesystem
    # to enable the changes, set dry_run to False, as in:
    # sds.dry_run = False

    # authenticate using either the token from
    # the .env file or in the config passed in
    sds.authenticate()

    # local_dir has your own local files that will be uploaded to the SDS
    reference_name: str = "my_spectrum_capture"
    local_dir: Path = Path(reference_name)

    # or, if the directory doesn't exist, let's create some fake data
    if not local_dir.exists():
        local_dir.mkdir(exist_ok=True)
        num_files = 10
        for file_idx in range(num_files):
            num_lines = randint(10, 100)  # noqa: S311
            file_name = f"capture_{file_idx}.csv"
            with (local_dir / file_name).open(mode="w", encoding="utf-8") as file_ptr:
                fake_nums = [random() for _ in range(num_lines)]  # noqa: S311
                file_ptr.write("\n".join(map(str, fake_nums)))

    # upload all files in a directory to the SDS
    # sds.dry_run = False   # uncomment to actually upload the files
    sds.upload(
        local_path=local_dir,  # may be a single file or a directory
        sds_path=reference_name,  # files will be created under this virtual directory
        verbose=True,  # shows a progress bar (default)
    )

    # download the files from an SDS directory
    # sds.dry_run = False
    local_downloads = Path("sds-downloads") / "files" / reference_name
    sds.download(
        from_sds_path=reference_name,  # files will be downloaded from this virtual dir
        to_local_path=local_downloads,  # download to this location (it may be created)
        overwrite=False,  # do not overwrite local existing files (default)
        verbose=True,  # shows a progress bar (default)
    )

    if not sds.dry_run:
        print("Downloaded files:")
        for file_path in local_downloads.iterdir():
            print(file_path)
    else:
        print("Turn off dry-run to download and write files.")
    ```

## Error Handling

The SDK provides context-aware exceptions that can be caught and handled in your code.

```py
# ======== Authentication ========
from pathlib import Path
from spectrums.client import Client
from spectrumx.errors import AuthError, NetworkError

sds = Client(host="sds.crc.nd.edu")
try:
    sds.authenticate()
except NetworkError as err:
    print(f"Failed to connect to the SDS: {err}")
    # check your host= parameter and network connection
    # if you're hosting the SDS Gateway, make sure it is accessible
except AuthError as err:
    print(f"Failed to authenticate: {err}")
    # TODO: take action

# ======== File operations ========

from time import sleep
from spectrumx.errors import NetworkError, SDSError, ServiceError

# ...
local_dir: Path = Path("my_spectrum_files")
reference_name: str = "my_spectrum_files"
is_success = False
retries_left: int = 5
while not is_success and retries_left > 0:
    try:
        retries_left -= 1
        # the sds.upload will restart a partial file transfer from zero,
        # but it won't re-upload already finished files.
        sds.upload(
            local_path=local_dir,
            sds_path=reference_name,
            verbose=True,
        )
        is_success = True
    except (NetworkError, ServiceError) as err:
        # NetworkError refers to connection issues between client and SDS Gateway
        # ServiceError refers to issues with the SDS Gateway itself (e.g. HTTP 500)
        # sleep longer with each retry, at least 5s, up to 5min
        sleep_time = max(5, 5 / (retries_left**2) * 60)
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
