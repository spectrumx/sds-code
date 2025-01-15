"""Pagination for SDS constructs."""

import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import Generic
from typing import Self
from typing import TypeVar

from loguru import logger as log

from spectrumx.errors import FileError
from spectrumx.gateway import GatewayClient
from spectrumx.models import SDSModel
from spectrumx.ops import files

if TYPE_CHECKING:
    from collections.abc import Generator

T = TypeVar("T", bound=SDSModel)


class _Unset:
    """Placeholder for an unset value to allow setting None."""


class Paginator(Generic[T]):
    """Manages the state for paginating through files in SDS.

    A Paginator instance may be iterated over to fetch and return parsed
    entries automatically. Note that network calls will happen in the background
    and fetching requests happen once per page. Iterating it also consumes the
    generator, so any yielded content should be stored if needed in the future.

    """

    def __init__(
        self,
        *,
        Entry: type[SDSModel],  # noqa: N803
        gateway: GatewayClient,
        sds_path: Path | str,
        dry_run: bool = False,
        page_size: int = 30,
        start_page: int = 1,
        total_matches: int | None = None,
        verbose: bool = False,
    ) -> None:
        if page_size <= 0:
            msg = "Page size must be a positive integer."
            raise ValueError(msg)
        if not isinstance(start_page, int) or start_page < 1:
            msg = "Start page must be a positive integer."
            raise ValueError(msg)
        if not isinstance(total_matches, int) and total_matches is not None:
            msg = "Total matches must be an integer."
            raise ValueError(msg)
        if not isinstance(sds_path, (Path, str)):
            msg = "SDS path must be a Path or str."
            raise TypeError(msg)
        if not isinstance(gateway, GatewayClient):
            msg = "Gateway client must be provided."
            raise TypeError(msg)
        if not issubclass(Entry, SDSModel):
            msg = "Entry must be a subclass of SDSModel."
            raise TypeError(msg)
        self.dry_run = dry_run
        self._Entry = Entry
        self._gateway = gateway
        self._next_page = start_page
        self._page_size = page_size
        self._sds_path = Path(sds_path)
        self._total_matches = total_matches if total_matches else 1
        self._verbose: bool = verbose

        # internal state
        self._has_fetched = False
        self._is_fetching: bool = False
        self._current_page_data: dict[str, Any] | None = None
        self._current_page_entries: Generator[T] = iter(())
        self._next_element: T | _Unset = _Unset()

    def __iter__(self) -> Self:
        """Returns the iterator object."""
        return self

    def __next__(self) -> T:
        """Returns the next entry in the pagination."""
        while self._next_element is not _Unset or self._has_next_page():
            try:
                self._next_element = next(self._current_page_entries)
            except StopIteration:
                try:
                    self._fetch_next_page()
                except StopIteration as err:
                    raise StopIteration(err) from err
            else:
                return self._next_element
        msg = "No more entries available."
        raise StopIteration(msg)

    def __len__(self) -> int:
        """Returns the total number of entries."""
        if not self._has_fetched:
            log.info("Fetching the first page of results.")
            self._fetch_next_page()
        return self._total_matches

    @property
    def _total_pages(self) -> int:
        """Calculates the total number of pages."""
        return (self._total_matches // self._page_size) + 1

    def _has_next_page(self) -> bool:
        """Checks if there is a next page available."""
        has_not_fetched = not self._has_fetched
        has_pages_left = self._next_page <= self._total_pages
        return has_not_fetched or has_pages_left

    def _fetch_next_page(self) -> None:
        """Fetches the next page of results."""
        if self._is_fetching:
            log.warning("Already fetching the next page.")
            return
        self._is_fetching = True
        # try-finally to unset self._is_fetching when done
        try:
            if not self._has_next_page():
                msg = "No more pages available."
                raise StopIteration(msg)
            if self.dry_run:
                log.info("Dry run enabled: generating a synthetic page")
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
                except FileError as err:
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
        _remaining_matches = self._total_matches - (self._next_page * self._page_size)
        _page_length = min(self._page_size, _remaining_matches)
        if _remaining_matches <= 0:
            msg = "No more entries available."
            raise StopIteration(msg)
        if issubclass(self._Entry, files.File):
            self._current_page_entries = (
                files.generate_sample_file(uuid.uuid4()) for _ in range(_page_length)
            )
        else:
            msg = f"Dry-run mode not implemented for this entry type: {self._Entry}"
            raise NotImplementedError(msg)

    def _ingest_new_page(self, raw_page: bytes) -> None:
        """Loads a raw page into memory and updates pagination state.

        The total number of pages and entry count might change between page
            requests, so this will update these control variables accordingly.
        """
        try:
            self._current_page_data = json.loads(raw_page)
        except json.JSONDecodeError as err:
            msg = "Failed to load page data: failed to decode the JSON response."
            raise TypeError(msg) from err
        if not isinstance(self._current_page_data, dict):
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
