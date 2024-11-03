"""
SpectrumX Data System SDK | basic usage example

This script demonstrates how to interact with the SDS using the SpectrumX SDK.
    It simulates the upload a directory of files to SDS and then downloads them
    back to a local directory. To actually upload and download files, the
    `dry_run` attribute of the `Client` instance must be set to `False`.
"""
# ruff: noqa: ERA001 # commented out code

from pathlib import Path
from random import randint
from random import random

from rich import traceback
from spectrumx import Client

# better traceback formatting with rich
traceback.install()


def main() -> None:
    """SDS client-server interaction example."""
    # NOTE: the SDS client-server interaction is stateless, so it is
    #   not recommended to have multiple clients writing to the same
    #   locations simultaneously, as they may overrule each other
    #   and cause loss of data.
    sds = Client(
        host="sds.crc.nd.edu",
        # env_file=Path(".env"),  # default
        # env_config={"SDS_SECRET_TOKEN": "my-custom-token"},  # overrides
    )

    # optionally enable logging for debugging (needs loguru installed)
    # spectrumx.enable_logging()

    # when in dry-run, no changes are made to the SDS or the local filesystem
    # when you're ready to actually upload and download files, set this to False
    sds.dry_run = True

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


if __name__ == "__main__":
    main()
