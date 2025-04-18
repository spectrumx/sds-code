"""Smoke-like checks for build acceptance, including basic usage of the SDK.

Do not run with pytest. This file doubles as documentation, so it doesn't
    have pytest constructs and has some code repetition between examples
    for learning purposes.

The goal is to be a quick way to check if client code runs, without strict
    assertions or coverage. As such, I'm calling these "checks" instead of
    "tests".

All SDK functions below should be called in dry_run mode to run in environments
    without credentials e.g. CI/CD deployments.

Run it as a standalone script between the package build and publishing steps.
Avoid adding third-party imports to this file.
"""
# ruff: noqa: ERA001, T201, I001

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
from random import randint
from random import random
from typing import TYPE_CHECKING

from spectrumx import Client
from spectrumx import enable_logging
import spectrumx

NOT_IMPLEMENTED = "This example is not yet implemented."
SDS_HOST = "sds-dev.crc.nd.edu"  # shouldn't matter for dry-runs

if TYPE_CHECKING:
    from spectrumx.models.files import File


def setup_module() -> None:
    """Setup any state specific to the execution of the given module."""
    Path("my_spectrum_files").mkdir(parents=True, exist_ok=True)


def teardown_module() -> None:
    """Teardown any state that was previously setup with a setup_module method."""
    Path("my_spectrum_files").rmdir()


def check_basic_usage() -> None:
    """Runs a basic usage run. Update this code to reflect readme changes."""

    print(f"Running basic usage check for v{spectrumx.__version__}...")

    # Example of files upload, listing, and download from SDS.

    # NOTE: the SDS client-server interaction is stateless, so it is
    #   not recommended to have multiple clients writing to the same
    #   locations simultaneously, as they may overrule each other
    #   and cause loss of data.
    sds = Client(
        host=SDS_HOST,
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
    reference_name: str = "my_spectrum_files"
    local_dir: Path = Path(reference_name)

    # or, if the directory doesn't exist, let's create some fake data
    if not local_dir.exists():
        local_dir.mkdir(exist_ok=True)
        num_files = 10
        for file_idx in range(num_files):
            num_lines = randint(10, 100)  # noqa: S311
            file_name = f"rf_run_{file_idx}.csv"
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


def check_error_handling() -> None:
    """Basic error handling examples."""

    # ======== Authentication ========

    from spectrumx.errors import AuthError, NetworkError

    sds = Client(host=SDS_HOST)
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


def check_file_listing_usage() -> None:
    """Basic file listing usage example."""

    sds = Client(host=SDS_HOST)
    sds.authenticate()
    reference_name: str = "my_spectrum_files"

    # list files in an SDS directory, without downloading them
    files_generator = sds.list_files(sds_path=reference_name)

    # Note that the returned object is a (lazy) generator, and it is consumed after
    # the first iteration. This has some benefits:
    #   1. avoids loading all file metadata in memory at once;
    #   2. reduces the time for the first page of files; and
    #   3. avoids making more server requests than necessary, while spacing them out.

    # If you need to iterate over the files multiple times, you
    # can get the first N files from the generator into a list:
    num_files: int = 3
    up_to_three_files: list[File] = []
    for _ in range(num_files):
        try:
            up_to_three_files.append(next(files_generator))
        except StopIteration:
            break  # no more to list; we have less than `num_files` files
    # `up_to_three_files` may be iterated over again

    # Converting the entire paginator into a list is not recommended
    # for a large or unknown number of files, for the reasons above.

    # otherwise, we can just iterate over the generator
    print("Remaining files from the generator:")
    for file_entry in files_generator:
        print(f"\tProcessing {file_entry.name} of size {file_entry.size} B...")
        # do_something_with_the_file(file_entry)


def check_capture_usage() -> None:
    """Basic capture usage example."""

    from spectrumx.models.captures import Capture, CaptureType

    sds = Client(host=SDS_HOST)
    sds.authenticate()

    new_capture = sds.captures.create(
        capture_type=CaptureType.RadioHound,
        top_level_dir=Path("/location/in/sds/"),
    )
    print(f"New capture ID: {new_capture.uuid}")

    my_rh_captures: list[Capture] = sds.captures.listing(
        capture_type=CaptureType.RadioHound
    )

    for capture in my_rh_captures:
        print(f"Capture {capture.uuid}: {capture.capture_props}")

    is_deleted = sds.captures.delete(
        new_capture.uuid  # retain as positional arg
    )
    print(f"Deleted capture {new_capture.uuid}: {is_deleted}")
    # double deleting a capture raises a CaptureError, unless in dry_run mode
    # (then the SDK can't determine whether the capture exists or not)


@dataclass
class CheckCaller:
    call_fn: Callable[[], None]
    name: str

    def __call__(self) -> None:
        self.call_fn()


def log_header(msg: str) -> None:
    print(f"======= {msg.upper()}")


def main() -> None:
    """Runs all checks."""

    enable_logging()

    # skips SSL verification if we're running against a development server
    os.environ["PYTEST_CURRENT_TEST"] = "check_build_acceptance.py::main"

    # check_basic_usage()
    all_checks = [
        CheckCaller(call_fn=check_basic_usage, name="Basic usage"),
        CheckCaller(call_fn=check_error_handling, name="Error handling"),
        CheckCaller(call_fn=check_file_listing_usage, name="File listing usage"),
        CheckCaller(call_fn=check_capture_usage, name="Capture usage"),
    ]
    for check in all_checks:
        log_header(f"Running {check.name} check...".upper())
        check()
        log_header(f"{check.name} check completed.\n\n")


if __name__ == "__main__":
    main()
