"""Utility functions for the SpectrumX SDK."""

import logging
import random
import string
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from blake3 import blake3 as Blake3  # noqa: N812
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
    """Converts a string to a boolean value, defaulting to False when invalid."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"t", "true", "1", "y", "yes", "on", "enabled"}
    return False


def get_random_line(length: int, *, include_punctuation: bool = True) -> str:
    """Generates a random string of a given length."""
    char_choices = (
        [*string.ascii_letters, *string.digits, *string.punctuation]
        if include_punctuation
        else [*string.ascii_letters, *string.digits]
    )
    return "".join(
        [
            random.choice(char_choices)  # noqa: S311
            for _ in range(length)
        ]
    )


def sum_blake3(file_path: Path) -> str:
    """Calculates the BLAKE3 checksum of a file."""
    checksum = Blake3()
    with file_path.open("rb") as file:
        for chunk in iter(lambda: file.read(4096), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


T = TypeVar("T")


def get_prog_bar(iterable: Iterable[T], *args, **kwargs) -> tqdm:  # pyright: ignore[reportMissingTypeArgument]
    """SDS standard progress bar."""
    default_options = {
        "unit": "files",
        "unit_scale": True,
        "ncols": 120,
        "colour": "yellow",
    }
    kwargs = {**default_options, **kwargs}

    return auto_tqdm.tqdm(iterable, *args, **kwargs)
