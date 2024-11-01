"""Utility functions for the SpectrumX SDK."""

import logging
from collections.abc import Iterable
from typing import TypeVar

from loguru import logger as log
from tqdm import auto as auto_tqdm
from tqdm import tqdm


def validate_file_permission_string(permissions: str) -> None:
    """Make sure a unix-like permissions string is valid."""
    perm_flags_len = 9
    assert (
        len(permissions) == perm_flags_len
    ), "Invalid permissions string. Expected 9 characters."
    valid_chars = {"r", "w", "x", "-"}
    assert set(permissions).issubset(
        valid_chars,
    ), "Invalid permission characters: use 'r', 'w', 'x', or '-'"
    assert all(
        permissions[idx * 3] in {"r", "-"} for idx in range(3)
    ), "Invalid read permissions"
    assert all(
        permissions[idx * 3 + 1] in {"w", "-"} for idx in range(3)
    ), "Invalid write permissions"
    assert all(
        permissions[idx * 3 + 2] in {"x", "-"} for idx in range(3)
    ), "Invalid execute permissions"


def log_user(msg: str) -> None:
    """Alias to log_user_info. Logs a message visible to SDK users."""
    log_user_info(msg)


def log_user_info(msg: str) -> None:
    """Logs an informational message to the user."""
    log.info(msg)
    logging.info(msg)


def log_user_warning(msg: str) -> None:
    """Logs a warning message to the user."""
    log.warning(msg)
    logging.warning(msg)


def log_user_error(msg: str) -> None:
    """Logs an error message to the user."""
    log.error(msg)
    logging.error(msg)


def into_human_bool(value: str) -> bool:
    """Converts a string to a boolean value."""
    return value.lower() in {"t", "true", "1", "y", "yes", "on", "enabled"}


T = TypeVar("T")


def prog_bar(iterable: Iterable[T], *args, **kwargs) -> tqdm:  # pyright: ignore[reportMissingTypeArgument]
    """SDS standard progress bar."""
    default_options = {
        "unit": "files",
        "unit_scale": True,
        "ncols": 120,
        "colour": "yellow",
    }
    kwargs = {**default_options, **kwargs}

    return auto_tqdm.tqdm(iterable, *args, **kwargs)
