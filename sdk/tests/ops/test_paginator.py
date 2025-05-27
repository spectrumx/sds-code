"""Tests for the paginator module."""

# ruff: noqa: SLF001
# pyright: reportPrivateUsage=false

from collections.abc import Generator
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest
from loguru import logger as log
from spectrumx.gateway import GatewayClient
from spectrumx.models.files import File
from spectrumx.ops.pagination import Paginator

log.trace("Placeholder log avoid reimporting or resolving unused import warnings.")


@pytest.fixture
def gateway() -> GatewayClient:
    """Fixture for the GatewayClient."""
    return MagicMock(spec=GatewayClient)


def test_paginator_respects_dry_run(gateway: GatewayClient) -> None:
    """Tests that the paginator respects the dry-run mode."""
    raw_first_page = b'{"count": 0, "results": []}'
    paginator_wet = Paginator[File](
        Entry=File,
        gateway=gateway,
        sds_path="/path/to/files",
        page_size=3,
        dry_run=False,
    )
    assert paginator_wet.dry_run is False, "Dry-run mode should be off"
    with patch.object(
        gateway, attribute="list_files", return_value=raw_first_page
    ) as mock_list_files:
        for _file_obj in paginator_wet:
            break
        mock_list_files.assert_called_once()
    del paginator_wet

    paginator_dry = Paginator[File](
        Entry=File,
        gateway=gateway,
        sds_path="/path/to/files",
        page_size=3,
        dry_run=True,
    )
    assert paginator_dry.dry_run is True, "Dry-run mode should be on"
    with patch.object(gateway, attribute="list_files") as mock_list_files:
        for _file_obj in paginator_dry:
            break
        mock_list_files.assert_not_called()


def test_paginator_dry_run_ingest(gateway: GatewayClient) -> None:
    """Tests the dry-run mode of the paginator."""
    page_size = 3
    expected_yield = int(2.5 * page_size)  # default for dry-run is 2.5 pages

    with patch.object(gateway, attribute="list_files") as mock_list_files:
        mock_list_files.side_effect = Exception("Should not be called in dry-run mode")
        paginator = Paginator[File](
            Entry=File,
            gateway=gateway,
            sds_path="/path/to/files",
            page_size=3,
            dry_run=True,
        )

        # initial state assertions
        assert paginator._has_fetched is False
        assert paginator._has_next_page is True
        assert paginator._next_page == 1
        assert paginator._total_matches == 1
        assert paginator._yielded_count == 0

        test_yield_count: int = 0

        # consume files and count them
        for file_obj in paginator:
            test_yield_count += 1
            assert isinstance(file_obj, File), "Expected a File instance"
        assert test_yield_count == expected_yield, (
            f"Expected {expected_yield} files, got {test_yield_count}"
        )


@pytest.mark.parametrize(
    argnames="fake_files",
    argvalues=[
        {"file_count": 3},  # change `target_count` below
    ],
    indirect=True,
)
def test_paginator_bool_non_empty(
    gateway: GatewayClient, fake_files: Generator[File]
) -> None:
    """A non-empty paginator should evaluate to True."""
    raw_first_page = _get_raw_page(
        fake_files=fake_files,
        target_count=3,
        page_size=3,
    )
    non_empty_paginator = Paginator[File](
        Entry=File,
        gateway=gateway,
        sds_path="/path/to/files",
        page_size=3,
        dry_run=False,
    )

    with patch.object(gateway, attribute="list_files", return_value=raw_first_page):
        assert non_empty_paginator, "Paginator should evaluate to True when not empty"


@pytest.mark.parametrize(
    argnames="fake_files",
    argvalues=[
        {"file_count": 0},  # change `target_count` below
    ],
    indirect=True,
)
def test_paginator_bool_empty(
    gateway: GatewayClient, fake_files: Generator[File]
) -> None:
    """An empty paginator should evaluate to False."""
    raw_empty_page = _get_raw_page(
        fake_files=fake_files,
        target_count=0,
        page_size=3,
    )
    empty_paginator = Paginator[File](
        Entry=File,
        gateway=gateway,
        sds_path="/path/to/files",
        page_size=3,
        dry_run=False,
    )
    with patch.object(gateway, attribute="list_files", return_value=raw_empty_page):
        assert not empty_paginator, "Paginator should evaluate to False when empty"


@pytest.mark.parametrize(
    argnames="fake_files",
    argvalues=[
        {"file_count": 4},  # change `target_count` below
    ],
    indirect=True,
)
def test_paginator_internal_state(
    gateway: GatewayClient, fake_files: Generator[File]
) -> None:
    """Assertions about the internal state of the paginator.

    This test is unfortunately highly coupled to the implementation,
        but it is helpful to catch subtle bugs in the implementation that
        won't be caught by the other tests.
    """

    # args
    target_count: int = 4  # same as `file_count` above
    first_page: int = 1
    page_size: int = 3  # 2 pages of 3 and 1 files each

    paginator = Paginator[File](
        Entry=File,
        gateway=gateway,
        sds_path="/path/to/files",
        page_size=page_size,
        dry_run=False,
    )

    raw_first_page = _get_raw_page(
        fake_files=fake_files,
        target_count=target_count,
        page_size=page_size,
    )
    raw_second_page = _get_raw_page(
        fake_files=fake_files,
        target_count=target_count,
        page_size=1,
    )

    # assertions about the initial state
    assert paginator._has_fetched is False
    assert paginator._has_next_page is True
    assert paginator._next_page == first_page
    assert paginator._yielded_count == 0
    assert paginator._total_matches == 1, (
        "Total matches is unknown (default=1) before the first page is fetched"
    )

    # assertions after the first page is fetched
    with patch.object(gateway, attribute="list_files", return_value=raw_first_page):
        assert len(paginator) == target_count  # this will fetch the first page

    assert paginator._has_fetched is True
    assert paginator._has_next_page is True
    assert paginator._next_page == first_page + 1
    assert paginator._total_matches == target_count
    assert paginator._yielded_count == 0, (
        "Yield count must be still zero after the first page is fetched"
    )

    # consume the first page
    test_yield_count: int = 0
    for _ in range(page_size):
        item = next(paginator)
        test_yield_count += 1
        assert isinstance(item, File), "Expected a File instance"
    assert test_yield_count == page_size, "Did not fill a page"
    assert paginator._yielded_count == page_size, (
        "Yield count does not match the items actually yielded (1st page)"
    )
    assert paginator._yielded_count == test_yield_count

    # assertions after the second and final page is fetched
    with patch.object(gateway, attribute="list_files", return_value=raw_second_page):
        for _ in range(1):  # 2nd page should have only 1 file
            item = next(paginator)
            test_yield_count += 1
            assert isinstance(item, File), "Expected a File instance"
    assert paginator._has_fetched is True
    assert paginator._has_next_page is False
    assert paginator._next_page == first_page + 2
    assert paginator._total_matches == target_count
    assert paginator._yielded_count == target_count, (
        "Yield count does not match the target count"
    )
    assert paginator._yielded_count == test_yield_count, (
        "Yield count does not match the items actually yielded (2nd page)"
    )

    # assertions of the final state
    for _file_obj in paginator:
        pytest.fail("Paginator should not yield any more items after the last page")
    assert test_yield_count <= target_count, "Yielded more items than expected"
    assert test_yield_count >= target_count, "Yielded fewer items than expected"


def _get_raw_page(
    fake_files: Generator[File], target_count: int, page_size: int
) -> bytes:
    """Consumes the `fake_files` generator and returns a page of serialized files."""
    fake_files_iter: Generator[File] = iter(fake_files)
    try:
        first_page_results = [
            next(fake_files_iter).model_dump_json(indent=4) for _ in range(page_size)
        ]
    except StopIteration:
        # raised only when the generator is empty: the usual StopIteration
        # (from exhausting a non-empty gen) will be caught by the for loop above.
        first_page_results = []
    raw_page_prefix = f'{{"count": {target_count}, "results": ['
    raw_page_suffix = "]}"
    raw_page_str = raw_page_prefix + ",".join(first_page_results) + raw_page_suffix
    return raw_page_str.encode()
