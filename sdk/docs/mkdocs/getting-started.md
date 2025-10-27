# Getting Started

## Installation

```bash
uv add spectrumx

# or one of:
#   poetry add spectrumx
#   pip install spectrumx
#   ...
```

### Example Notebooks

+ [SpectrumX SDK walkthrough](https://github.com/crcresearch/spx-events/blob/main/demos/data_system/walkthrough.ipynb)

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

2. Then, in your Python script or Jupyter notebook

    > See [`./tests/e2e_examples/check_build_acceptance.py`](https://github.com/spectrumx/sds-code/blob/master/sdk/tests/e2e_examples/check_build_acceptance.py) for a live up-to-date example.

    ```python
    from pathlib import Path
    from random import randint, random
    from spectrumx.client import Client

    # Example of files upload, listing, and download from SDS.

    # NOTE: the SDS client-server interaction is stateless, so it is
    #   not recommended to have multiple clients writing to the same
    #   locations simultaneously, as they may overrule each other
    #   and cause loss of data. See "Concurrent Access" in the
    #   usage guide to learn more.
    sds = Client(
        host="sds.crc.nd.edu",
        # env_file=Path(".env"),  # default, recommended to keep tokens out of version control
        # env_config={"SDS_SECRET_TOKEN": "my-custom-token"},  # alternative way to pass the access token
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
    upload_results = sds.upload(
        local_path=local_dir,  # may be a single file or a directory
        sds_path=reference_name,  # files will be created under this virtual directory
        verbose=True,  # shows a progress bar (default)
    )
    success_results = [success for success in upload_results if success]
    failed_results = [success for success in upload_results if not success]
    assert len(failed_results) == 0, (
        f"No failed uploads should be present: {failed_results}"
    )
    log.debug(f"Uploaded {len(success_results)} assets.")

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

### Error Handling

The SDK provides context-aware exceptions that can be caught and handled in your code.

```py
# ======== Authentication ========
from pathlib import Path
from spectrumx.client import Client
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
from spectrumx.errors import NetworkError
from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.errors import ServiceError
from loguru import logger as log

# ...
local_dir: Path = Path("my_spectrum_files")
reference_name: str = "my_spectrum_files"
retries_left: int = 5
is_success: bool = False
uploaded_files: list[File] = []
while not is_success and retries_left > 0:
    try:
        retries_left -= 1

        # `sds.upload()` will restart a partial file transfer from zero,
        # but it won't re-upload already finished files.
        upload_results: list[Result[File]] = sds.upload(
            local_path=local_dir,
            sds_path=reference_name,
            verbose=True,
        )

        # Since `upload()` is a batch operation, some files may succeed and some
        #   may fail. The return value of `sds.upload` stored in `upload_results`
        #   is a list of `Result` objects:
        # A `Result` wraps either the value of a variable (in this case the File
        #   object that was uploaded) or an exception. Here's how we can check if
        #   there were any failed uploads:
        success_results = [success for success in upload_results if success]
        failed_results = [success for success in upload_results if not success]

        log.debug(f"Uploaded {len(success_results)} assets.")
        log.warning(f"Failed to upload {len(failed_results)} assets")

        # calling a successful result will return the value it holds
        uploaded_files = [result() for result in success_results]

        # And calling a failed result will raise the exception it holds.
        # Here we re-raise it to handle retries with the except blocks below,
        #   based on the exception raised:
        for result in failed_results:
            result()  # will raise

    except (NetworkError, ServiceError) as err:
        # NetworkError refers to connection issues between client and SDS Gateway
        # ServiceError refers to issues with the SDS Gateway itself (e.g. HTTP 500)
        # sleep longer with each retry, at least 5s, up to 5min
        sleep_time = max(5, 5 / (retries_left**2) * 60)
        log.error(f"Error: {err}")
        log.warning(f"Failed to reach the gateway; sleeping {sleep_time}s")
        if retries_left > 0:
            sleep(sleep_time)
        continue
    except SDSError as err:
        log.error(f"Another SDS error occurred: {err}")
        # other errors might include e.g. OSError
        #   if listed files cannot be found.
        # TODO: take action or break
        break

log.debug(f"Uploaded files: {uploaded_files}")
```
