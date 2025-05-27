"""Pagination for SDS constructs."""

import json
import sys
import time
import uuid
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Any
from typing import Generic
from typing import TypeVar

# python 3.10 backport
if sys.version_info < (3, 11):  # noqa: UP036
    from typing_extensions import Self  # noqa: UP035 # Required backport
else:
    from typing import Self

from loguru import logger as log

from spectrumx.errors import FileError
from spectrumx.errors import Unset
from spectrumx.gateway import GatewayClient
from spectrumx.models import SDSModel
from spectrumx.ops import files

if TYPE_CHECKING:
    from collections.abc import Generator

T = TypeVar("T", bound=SDSModel)


class Paginator(Generic[T]):
    """Manages the state for paginating through files in SDS.

    A Paginator instance may be iterated over to fetch and return parsed
    entries automatically. Note that network calls will happen in the background
    and fetching requests happen once per page. Iterating it also consumes the
    generator, so any yielded content should be stored if needed in the future.

    ## Usage example

    ```
    file_paginator = Paginator[File](
        Entry=File,
        gateway=gateway,
        sds_path="/path/to/files",
        dry_run=False,
        verbose=True,
    )
    print(f"Total files matched: {len(file_paginator)}")
    # len() will fetch the first page

    for my_file in file_paginator:
        print(f"Processing file: {my_file.name}")
        process_file(my_file)
        # new pages are fetched automatically

    for _my_file in file_paginator:
        msg = "This will not run, as the paginator was consumed."
        raise AssertionError(msg)
    ```
    """

    def __init__(
        self,
        *,
        Entry: type[SDSModel],  # noqa: N803
        gateway: GatewayClient,
        sds_path: PurePosixPath | Path | str,
        dry_run: bool = False,
        page_size: int = 30,
        start_page: int = 1,
        total_matches: int | None = None,
        verbose: bool = False,
    ) -> None:
        """Initializes the paginator with the required parameters.

        Args:
            Entry:          The SDSModel subclass to use when parsing the entries.
            gateway:        The gateway client to use for fetching pages.
            sds_path:       The SDS path to paginate through.
            dry_run:        If True, will generate synthetic pages instead of fetching.
            page_size:      The number of entries to fetch per page.
            start_page:     The page number to start fetching from.
            total_matches:  The total number of entries across all pages.
            verbose:        If True, will log more information about the pagination.
        """

        # TODO: generalize this to any SDSModel subclass (too coupled to File now)

        if page_size <= 0:  # pragma: no cover
            msg = "Page size must be a positive integer."
            raise ValueError(msg)
        if not isinstance(start_page, int) or start_page < 1:  # pragma: no cover
            msg = "Start page must be a positive integer."
            raise ValueError(msg)
        if (
            not isinstance(total_matches, int) and total_matches is not None
        ):  # pragma: no cover
            msg = "Total matches must be an integer."
            raise ValueError(msg)
        if not isinstance(sds_path, (PurePosixPath, Path, str)):  # pragma: no cover
            msg = "SDS path must be a PurePosixPath, Path, or str."
            raise TypeError(msg)
        if not isinstance(gateway, GatewayClient):  # pragma: no cover
            msg = "Gateway client must be provided."
            raise TypeError(msg)
        if not issubclass(Entry, SDSModel):  # pragma: no cover
            msg = "Entry must be a subclass of SDSModel."
            raise TypeError(msg)
        self.dry_run = dry_run
        self._Entry = Entry
        self._gateway = gateway
        self._next_page = start_page
        self._page_size = page_size
        self._sds_path = PurePosixPath(sds_path)
        self._total_matches = total_matches if total_matches else 1
        self._verbose: bool = verbose

        # internal state
        self._has_fetched = False
        self._is_fetching: bool = False
        self._current_page_data: dict[str, Any] | None = None
        self._current_page_entries: Generator[T] = iter(())
        self._next_element: T | Unset = Unset()
        self._yielded_count: int = 0

    def __iter__(self) -> Self:
        """Returns the iterator object."""
        return self

    def __next__(self) -> T:
        """Returns the next entry in the pagination."""
        while self._next_element is not Unset or self._has_next_page:
            try:
                self._next_element = next(self._current_page_entries)
            except StopIteration:
                try:
                    self._fetch_next_page()
                    self._debug("Fetched the next page.")
                except StopIteration as err:
                    self._debug("No more pages available.")
                    raise StopIteration(err) from err
            else:
                self._yielded_count += 1
                return self._next_element
        # execution should never reach here
        msg = "Internal paginator error."  # pragma: no cover
        raise RuntimeError(msg)  # pragma: no cover

    def __len__(self) -> int:
        """Returns the total number of entries."""
        if not self._has_fetched:
            self._debug("Fetching the first page of results.")
            self._fetch_next_page()
        return self._total_matches

    def __bool__(self) -> bool:
        """Returns True if there are entries to iterate over."""
        if not self._has_fetched:
            self._debug("Fetching the first page of results.")
            self._fetch_next_page()
        return self._total_matches > 0

    @property
    def _total_pages(self) -> int:
        """Calculates the total number of pages."""
        return (self._total_matches // self._page_size) + 1

    def _debug(self, message: str, depth: int = 1) -> None:
        """Logs a debug message if verbose mode is enabled."""
        if self._verbose:  # pragma: no cover
            log.opt(depth=depth).debug(message)

    @property
    def _has_next_page(self) -> bool:
        """Checks if there is a next page available."""
        has_not_fetched = not self._has_fetched
        has_pages_left = self._next_page <= self._total_pages
        return has_not_fetched or has_pages_left

    def _fetch_next_page(self) -> None:
        """Fetches the next page of results."""
        if self._is_fetching:  # pragma: no cover
            log.warning("Already fetching the next page.")
            return
        self._is_fetching = True
        # try-finally to unset self._is_fetching when done
        try:
            if not self._has_next_page:
                msg = "No more pages available."
                raise StopIteration(msg)
            if self.dry_run:
                self._debug("Dry run enabled: generating a synthetic page")
                self._ingest_fake_page()
            else:
                # try to fetch the next page
                try:
                    raw_page = self._gateway.list_files(
                        sds_path=self._sds_path,
                        page=self._next_page,
                        page_size=self._page_size,
                        verbose=self._verbose,
                    )
                    self._ingest_new_page(raw_page)
                except FileError as err:  # pragma: no cover
                    # log an unexpected FileError if it happens
                    if "invalid page" not in str(err).lower():
                        msg = "Unexpected error while fetching the next page:"
                        log.exception(msg)
                    msg = "No more pages available."
                    raise StopIteration(msg) from err
            self._next_page += 1
            self._has_fetched = True  # `len(self)` is now valid
        finally:
            self._is_fetching = False

    def _ingest_fake_page(self) -> None:
        """Loads a fake page into memory for dry-run mode."""
        self._total_matches = int(self._page_size * 2.5)  # targeting 3 pages
        _remaining_matches = self._total_matches - self._yielded_count
        _page_length = min(self._page_size, _remaining_matches)
        if self._yielded_count >= self._total_matches:  # pragma: no cover
            msg = "No more entries available."
            raise StopIteration(msg)
        # generate page
        if issubclass(self._Entry, files.File):
            # TODO: merge self._current_page_entries with the new
            #   entries (lazily) to allow pre-fetching a page, or
            #   fetching multiple pages at once.
            self._current_page_entries = (
                files.generate_sample_file(uuid.uuid4()) for _ in range(_page_length)
            )
        else:  # pragma: no cover
            msg = f"Dry-run mode not implemented for this entry type: {self._Entry}"
            raise NotImplementedError(msg)

    def _ingest_new_page(self, raw_page: bytes) -> None:
        """Loads a raw page into memory and updates pagination state.

        The total number of pages and entry count might change between page
            requests, so this will update these control variables accordingly.
        """
        try:
            self._current_page_data = json.loads(raw_page)
        except json.JSONDecodeError as err:  # pragma: no cover
            msg = "Failed to load page data: failed to decode the JSON response."
            raise TypeError(msg) from err
        if not isinstance(self._current_page_data, dict):  # pragma: no cover
            msg = "Failed to load page data: expected a dictionary from JSON."
            raise TypeError(msg)
        if "count" in self._current_page_data:
            self._total_matches = self._current_page_data["count"]
        self._current_page_entries = (
            (
                self._Entry(**entry_data)
                for entry_data in self._current_page_data["results"]
            )
            if "results" in self._current_page_data
            else iter(())
        )


def _process_file_fake(my_file: files.File) -> None:  # pragma: no cover
    """Sleeps a bit."""
    time.sleep(0.07)


def main() -> None:  # pragma: no cover
    """Usage example for paginator."""
    log.info("Running the main script.")
    file_paginator = Paginator[files.File](
        Entry=files.File,
        gateway=GatewayClient(
            host="localhost",
            api_key="does-not-matter-in-dry-run",
        ),
        sds_path="/path/to/files",
        page_size=10,
        dry_run=True,  # in dry-run this should always generate 2.5 pages
        verbose=True,
    )
    log.info(f"Total files matched: {len(file_paginator)}")
    processed_count: int = 0
    for my_file in file_paginator:
        log.info(f"Processing file: {my_file.name}")
        _process_file_fake(my_file)
        processed_count += 1
        # new pages are fetched automatically

    log.info(f"Processed {processed_count} / {len(file_paginator)} files.")

    log.info("Trying another loop:")
    for _my_file in file_paginator:
        msg = "This will not run, as the paginator was consumed."
        raise AssertionError(msg)
    log.info("No more files to process.")

    log.info("Paginator demo finished.")


if __name__ == "__main__":
    main()
