"""Utility functions for the SpectrumX SDK."""

from __future__ import annotations

import contextlib
import contextvars
import importlib.metadata
import json
import logging
import os
import platform
import random
import re
import string
import tempfile
from datetime import UTC
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any
from typing import NoReturn
from typing import TypeVar
from typing import cast

from blake3 import blake3 as Blake3  # noqa: N812
from loguru import logger as log
from tqdm import auto as auto_tqdm
from tqdm import tqdm

from spectrumx.vendor.xdg_base_dirs import xdg_state_home

if TYPE_CHECKING:
    from collections.abc import Iterable

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


def into_human_bool(value: str | int | bool) -> bool:  # noqa: FBT001
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
        from IPython import (  # pyright: ignore[reportMissingModuleSource, reportMissingImports]  # noqa: PLC0415 # pyrefly: ignore[missing-import]
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


def get_prog_bar(
    iterable: Iterable[T] | None = None, *args, **kwargs
) -> tqdm[T] | tqdm[NoReturn]:  # pyrefly: ignore[bad-specialization]
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

    return cast(
        "tqdm[T]",  # pyrefly: ignore[bad-specialization]
        auto_tqdm.tqdm(iterable, *args, **kwargs),
    )


# --- Structured Logging ---


class LogCategory(StrEnum):
    """Categories for structured log messages."""

    LOG = "log"
    CONFIG = "config"
    AUTH = "auth"
    NETWORK = "network"
    FILESYSTEM = "filesystem"
    DOWNLOAD = "download"
    UPLOAD = "upload"


LOG_CATEGORY_LOG = LogCategory.LOG


_log_context: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "_log_context", default=None
)

_persistent_context: dict[str, Any] = {}
_structured_sink_id: int | None = None
_current_log_path: Path | None = None


class LogContext:
    """Context manager for scoped structured logging context binding."""

    def __init__(self, **kwargs: Any) -> None:
        self._kwargs = kwargs
        self._token: contextvars.Token[dict[str, Any]] | None = None

    def __enter__(self) -> None:
        current = (_log_context.get() or {}).copy()
        current.update(self._kwargs)
        self._token = _log_context.set(current)

    def __exit__(self, *args: object) -> None:
        if self._token is not None:
            _log_context.reset(self._token)


# Alias for LogContext - used by uploads.py
log_context = LogContext


def set_persistent_log_context(**kwargs: Any) -> None:
    """Set persistent context fields that appear on all log lines."""
    _persistent_context.update(kwargs)


def _get_default_log_path() -> Path:
    """Resolve default structured log path: XDG state home > temp dir."""
    try:
        base = xdg_state_home() / "spectrumx" / "logs"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
    except (ImportError, OSError):
        return Path(tempfile.gettempdir()) / "spectrumx_sdk.jsonl"


def _emit_boot_message(log_path: Path) -> None:
    """Write system info boot message to the log file."""
    try:
        sdk_version = importlib.metadata.version("spectrumx")
    except importlib.metadata.PackageNotFoundError:
        sdk_version = "unknown"

    boot_entry = {
        "ts": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
        "lvl": "INFO",
        "cat": LogCategory.LOG,
        "msg": "system info",
        "sdk_version": sdk_version,
        "os": platform.platform(),
        "python": platform.python_version(),
        "log_file": str(log_path),
    }
    try:
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(boot_entry, default=str) + "\n")
    except OSError:
        pass


def _structured_log_sink(message: Any) -> None:
    """Loguru function sink: reads ContextVar, writes JSON line to file."""
    if _current_log_path is None:
        return

    rec = message.record
    msg_str = rec["message"].rstrip()

    entry: dict[str, Any] = {
        "ts": rec["time"].isoformat(),
        "pid": rec["process"].id,
        "lvl": rec["level"].name,
        "cat": rec.get("extra", {}).get("cat", LogCategory.LOG),
        "msg": msg_str,
    }

    # Merge persistent context
    entry.update({k: v for k, v in _persistent_context.items() if v is not None})

    # Merge scoped context
    ctx = _log_context.get() or {}
    entry.update({k: v for k, v in ctx.items() if v is not None})

    # Extract exc_info from loguru record (for error log lines)
    exc_info = rec.get("exception")
    if exc_info is not None and exc_info.type is not None:
        entry["exc_info"] = f"{exc_info.type.__name__}: {exc_info.value}"

    try:
        with _current_log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        pass


def enable_structured_logging(log_path: Path | str | None = None) -> None:
    """Enable or reconfigure the structured JSONL logging sink."""
    global _structured_sink_id, _current_log_path  # noqa: PLW0603

    if _structured_sink_id is not None:
        with contextlib.suppress(Exception):
            log.remove(_structured_sink_id)

    # Resolve path
    resolved = Path(log_path) if log_path is not None else _get_default_log_path()

    _current_log_path = resolved
    parent = resolved.parent
    parent.mkdir(parents=True, exist_ok=True)

    # Emit system info boot message every time the logger is initialized
    _emit_boot_message(resolved)

    try:
        _structured_sink_id = log.add(
            _structured_log_sink,
            format="{message}",
            filter=lambda record: True,
        )
    except Exception:  # noqa: BLE001
        _structured_sink_id = None


def reset_structured_logging() -> None:
    """Reset structured logging state. Useful for tests."""
    global _structured_sink_id, _current_log_path  # noqa: PLW0603
    if _structured_sink_id is not None:
        with contextlib.suppress(Exception):
            log.remove(_structured_sink_id)
    _structured_sink_id = None
    _current_log_path = None
    _persistent_context.clear()
    _log_context.set(None)
