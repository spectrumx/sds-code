"""Utility functions for the SpectrumX SDK."""

import logging
import os
import random
import re
import string
from collections.abc import Iterable
from pathlib import Path
from typing import TypeVar

from blake3 import blake3 as Blake3  # noqa: N812
from loguru import logger as log
from tqdm import auto as auto_tqdm
from tqdm import tqdm

logger = logging.getLogger(__name__)


def validate_file_permission_string(permissions: str) -> None:
    """Make sure a unix-like permissions string is valid."""
    perm_flags_len = 9
    assert len(permissions) == perm_flags_len, (
        "Invalid permissions string. Expected 9 characters."
    )
    valid_chars = {"r", "w", "x", "-"}
    assert set(permissions).issubset(
        valid_chars,
    ), "Invalid permission characters: use 'r', 'w', 'x', or '-'"
    assert all(permissions[idx * 3] in {"r", "-"} for idx in range(3)), (
        "Invalid read permissions"
    )
    assert all(permissions[idx * 3 + 1] in {"w", "-"} for idx in range(3)), (
        "Invalid write permissions"
    )
    assert all(permissions[idx * 3 + 2] in {"x", "-"} for idx in range(3)), (
        "Invalid execute permissions"
    )


def log_user(msg: str, depth: int = 1) -> None:
    """Alias to log_user_info. Logs a message visible to SDK users."""
    log_user_info(msg, depth=depth + 1)


def log_user_info(msg: str, depth: int = 1) -> None:
    """Logs an informational message to the user."""
    log.opt(depth=depth).info(msg)
    logger.info(msg)


def log_user_warning(msg: str, depth: int = 1) -> None:
    """Logs a warning message to the user."""
    log.opt(depth=depth).warning(msg)
    logger.warning(msg)


def log_user_error(msg: str, depth: int = 1) -> None:
    """Logs an error message to the user."""
    log.opt(depth=depth).error(msg)
    logger.error(msg)


def into_human_bool(value: str | int | bool) -> bool:
    """Converts a string to a boolean value, defaulting to False when invalid."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.lower() in {"t", "true", "1", "y", "yes", "on", "enabled"}
    return False


def is_running_in_notebook() -> bool:
    """Check if the current environment is a Jupyter notebook."""
    try:
        from IPython import (  # pyright: ignore[reportMissingModuleSource, reportMissingImports]
            get_ipython,  # pyright: ignore[reportPrivateImportUsage]
        )

        if "ZMQInteractiveShell" in str(get_ipython()):
            running_in_notebook = True
        else:
            running_in_notebook = False
    except ImportError:
        running_in_notebook = False
    return running_in_notebook


def is_test_env() -> bool:
    """Returns whether the current environment is a test environment.

    Useful for:
        + Deciding if SSL verification can be skipped;
        + Whether debug logs should be enabled on error;
    """
    env_var = os.getenv("PYTEST_CURRENT_TEST", default=None)
    return env_var is not None


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


def clean_local_path(local_path: Path) -> Path:
    """Hack to remove what looks like an SDS user ID from local path.

    This is non-critical and will be unnecessary after some gateway changes...
    """
    # match email-like strings at the second level
    n_level = 2 if local_path.is_absolute() else 1
    email_like_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    local_path_2nd_level: str = local_path.parts[n_level]
    is_dirty = bool(re.match(email_like_pattern, string=local_path_2nd_level))
    if not is_dirty:
        return local_path
    # remove the top 2 levels
    return Path(*local_path.parts[n_level + 1 :])


T = TypeVar("T")


def get_prog_bar(iterable: Iterable[T], *args, **kwargs) -> tqdm:  # pyright: ignore[reportMissingTypeArgument]
    """SDS standard progress bar."""
    default_options = {
        "unit": "files",
        "unit_scale": True,
        # width in the terminal is in characters; in jupyter it's in pixels
        "ncols": 800 if is_running_in_notebook() else 120,
        # adjust colors for visibility:
        #   terminals usually have a dark bg; jupyter outputs usually have a light bg
        "colour": "green" if is_running_in_notebook() else "yellow",
    }
    kwargs = {**default_options, **kwargs}

    return auto_tqdm.tqdm(iterable, *args, **kwargs)
