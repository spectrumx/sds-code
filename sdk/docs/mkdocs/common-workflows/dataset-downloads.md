# SDS Dataset Downloads

+ [SDS Dataset Downloads](#sds-dataset-downloads)
    + [Checklist](#checklist)
    + [Context](#context)
    + [Script](#script)

The script below demonstrates how to download all files from a specified dataset
using the SpectrumX SDK. It includes error handling and retry logic to manage
potential download issues.

## Checklist

Checklist to use the script below:

+ [ ] Have a Python environment with `spectrumx` and `loguru` installed.
+ [ ] Make sure the `download_path` location has enough disk space to store the dataset
    you are downloading.
+ [ ] Set up your SDS API key in a `.env` file in the same directory as the script
    below. Generate a key at <https://sds.crc.nd.edu/users/generate-api-key-form/>
+ [ ] Update the `dataset_uuid_str` variable with the UUID of the dataset you want to
    download.
+ [ ] Follow any other "`TODO`" comments in the script.

## Context

It also features exponential backoff for retries in case of intermittent connection
or service issues. The total wait time before giving up with the default settings
is capped at around 4 hours, but may be adjusted by changing the `max_sleep_time_sec`
and `retries_left` variables.

When retrying, the SDK will check which dataset files have already been downloaded
and will only attempt to download the missing files. As a result, retrying a failed
download has little overhead.

## Script

```python
#!/usr/bin/env python
"""Download all files from a specified SDS dataset with retry logic.

For documentation, see https://sds.crc.nd.edu/sdk/

"""

import time
from pathlib import Path
from uuid import UUID

from loguru import logger as log
from spectrumx import Client
from spectrumx.errors import SDSError


def main() -> None:
    # Initialize the client with your SDS host
    client = Client(
        host="sds.crc.nd.edu",
        # TODO: create a .env file with your SDS API token for authentication
        # env_file=Path(".env"),  # default, recommended to keep tokens out of version control
    )

    # when in dry-run (default), no changes are made to the SDS or the local filesystem
    # to enable the changes, set dry_run to False, as in:
    client.dry_run = False  # ⚠️ This is required to actually download files!

    # authenticate using either the token from the .env file or in the config passed in.
    # This will raise an spectrumx.errors.AuthError if authentication fails, and it's
    # useful to isolate API access issues; otherwise it is not required to be called
    # explicitly before other operations, as each API call carries auth information.
    client.authenticate()

    # TODO: specify the dataset UUID and local download path
    #   Where to find the dataset's UUID:
    #   1. Log into the SDS. https://sds.crc.nd.edu/
    #   2. Navigate to the dataset listing page. https://sds.crc.nd.edu/users/dataset-list/
    #   3. Locate the dataset you want to download and click on its name. A modal will open.
    #   4. The modal has detailed infomation on the dataset. Beside its name, you will see a
    #       "Copy" button. Clicking it will copy the dataset's UUID to your clipboard.
    #       a UUID has the format "xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx", where each "x"
    #       is a hexadecimal digit.
    #  5. Paste the UUID string below, replacing the placeholder value.
    dataset_uuid_str = "xxxxxxxx-xxxx-4xxx-xxxx-xxxxxxxxxxxx"
    dataset_uuid = UUID(dataset_uuid_str)

    # TODO: make sure this download location has enough disk space for the dataset you
    #   are downloading. The total size of the dataset can be found on its details modal
    #   in the SDS web interface. On Linux machines, you can use this command:
    #       df --si .
    #   SI units match the ones used in the SDS web interface.
    download_path = Path("./downloaded_dataset")

    log.info(f"Downloading dataset: {dataset_uuid_str}")
    log.info(f"Download path: {download_path}")

    # loop control
    is_success: bool = False
    retries_left: int = 50
    sleep_time_sec: int = 1
    max_sleep_time_sec: int = 300
    is_first_run = True
    # max total wait is under max_sleep_time_sec * retries_left:
    #   300 * 50 < 15'000 seconds, or < 4h 10min
    # after this time with no progress, the script will give up the download

    while not is_success and retries_left > 0:
        if not is_first_run:
            # wait before next retry, with exponential backoff in case
            # it's an intermittend connection or service issue
            sleep_time_sec *= 2
            time.sleep(min(sleep_time_sec, max_sleep_time_sec))
        is_first_run = False
        retries_left -= 1
        try:
            # download all files in the dataset
            results = client.download_dataset(
                dataset_uuid=dataset_uuid,
                to_local_path=download_path,
                overwrite=False,  # set to True to overwrite existing local files
                verbose=True,  # show progress bars
            )
        except SDSError as err:
            log.exception(f"Error downloading dataset: {err}")
            continue
        except Exception as err:
            log.exception(f"Unexpected error: {err}")
            continue

        # no connection errors, reset sleep time
        sleep_time_sec = 1

        # Check results for any errors
        successful_downloads = [
            r for r in results if r
        ]  # Result objects are truthy if successful
        failed_downloads = [
            r for r in results if not r
        ]  # Result objects are falsy if failed

        log.success(f"Successfully downloaded: {len(successful_downloads)} files")
        log.info(f"Failed downloads: {len(failed_downloads)} files")

        if not failed_downloads:
            is_success = True
            break

        log.info("\nFailed downloads:")
        for result in failed_downloads:
            # TIP: calling result() will re-raise the exception if you prefer
            #   to handle it here instead of just logging it.
            file_info = result.error_info.get("file", {})
            file_name = (
                file_info.get("name", "Unknown")
                if isinstance(file_info, dict)
                else "Unknown"
            )
            msg = f"  - {file_name}: {result.exception_or(RuntimeError('Unknown download error'))}"
            log.error(msg)


if __name__ == "__main__":
    main()
```
