"""Tests for the utils module."""

# pyright: reportPrivateUsage=false

import importlib.metadata
import sys
import tempfile
import types
import warnings
from contextlib import contextmanager
from pathlib import Path

import pytest
import urllib3
from loguru import logger as log
from spectrumx import utils
from tqdm import tqdm


class RecordingProgBar:
    """State-recording progress bar: appends each update's increment to a list."""

    def __init__(self) -> None:
        self.updates: list[int] = []

    def update(self, n: int = 1) -> None:
        self.updates.append(n)

    def close(self) -> None:
        """No-op close for API compatibility with tqdm."""


@contextmanager
def disable_ssl_warnings():
    with warnings.catch_warnings():
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        yield None


@pytest.mark.parametrize(
    "perm",
    [
        "rwxrwxrwxr",
        "rw-rwxrwxrwx",
        "rwxr-xr",
    ],
)
def test_permission_string_invalid_length(perm: str) -> None:
    """Invalid-length permission string raises AssertionError."""
    with pytest.raises(AssertionError):
        utils.validate_file_permission_string(perm)


@pytest.mark.parametrize(
    "perm",
    [
        "rwxrwxrws",
        "rw_______",
        "rwxrwxrw?",
    ],
)
def test_permission_string_invalid_chars(perm: str) -> None:
    """Invalid-character permission string raises AssertionError."""
    with pytest.raises(AssertionError):
        utils.validate_file_permission_string(perm)


@pytest.mark.parametrize(
    "perm",
    [
        "rwxrwxwxr",
        "wrxrwxrwx",
        "rwxrxwrwx",
        "--------r",
    ],
)
def test_permission_string_out_of_order(perm: str) -> None:
    """Out-of-order permission string raises AssertionError."""
    with pytest.raises(AssertionError):
        utils.validate_file_permission_string(perm)


@pytest.mark.parametrize(
    "perm",
    [
        "rwxrwxrwx",
        "rw-rw-r--",
        "r--r--r--",
        "---------",
        "rwx------",
    ],
)
def test_permission_string_valid(perm: str) -> None:
    """Valid permission string passes validation."""
    utils.validate_file_permission_string(perm)


@pytest.mark.parametrize(
    "value",
    [
        True,
        1,
        "true",
        "True",
        "TrUe",
        "TRUE",
        "ON",
        "1",
        "t",
        "y",
        "yes",
        "on",
        "enabled",
    ],
    ids=repr,
)
def test_into_bool_truthy(value) -> None:
    """Each truthy value converts to True."""
    assert utils.into_human_bool(value) is True


@pytest.mark.linux
@pytest.mark.darwin
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Path("/files/user@domain.com/clean/path"), Path("clean/path")),
        (Path("files/user@domain.ai/clean/path"), Path("clean/path")),
        (Path("___/user@domain.ai/clean/path"), Path("clean/path")),
        (Path("example.com/change/path"), Path("example.com/change/path")),
        (
            Path("user@domain.dev/still/clean/path"),
            Path("user@domain.dev/still/clean/path"),
        ),
        (Path("yet/another/path"), Path("yet/another/path")),
    ],
    ids=[
        "abs_files_domain",
        "rel_files_domain",
        "abs_no_files_prefix",
        "no_email_left_untouched",
        "email_at_deeper_level_untouched",
        "bare_path_untouched",
    ],
)
def test_clean_local_path(value: Path, expected: Path) -> None:
    """Each path is cleaned only when an email-like segment sits at the 2nd level."""
    assert utils.clean_local_path(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        False,
        0,
        "false",
        "False",
        "FalSe",
        "FALSE",
        "OFF",
        "0",
        "f",
        "n",
        "no",
        "off",
        "disabled",
    ],
    ids=repr,
)
def test_into_bool_falsey(value) -> None:
    """Each falsey value converts to False."""
    assert utils.into_human_bool(value) is False


def test_credit_unstreamed_file_bytes_credits_remaining() -> None:
    """Unstreamed bytes are credited to the progress bar and the shared counter."""
    file_size = 1000
    bytes_streamed = 400
    credited_bytes = file_size - bytes_streamed
    prog_bar = RecordingProgBar()
    bytes_accounted = [bytes_streamed]

    credited = utils.credit_unstreamed_file_bytes(
        file_size=file_size,
        bytes_streamed=bytes_streamed,
        prog_bar=prog_bar,
        bytes_accounted=bytes_accounted,
    )

    assert credited == credited_bytes
    assert bytes_accounted[0] == file_size
    # state assertion against the recording fake, not a mock call recorder
    assert prog_bar.updates == [credited_bytes]


def test_credit_unstreamed_file_bytes_noop_when_fully_streamed() -> None:
    """No credit is applied when all bytes were already streamed."""
    file_size = 1000
    prog_bar = RecordingProgBar()
    bytes_accounted = [file_size]

    credited = utils.credit_unstreamed_file_bytes(
        file_size=file_size,
        bytes_streamed=file_size,
        prog_bar=prog_bar,
        bytes_accounted=bytes_accounted,
    )

    assert credited == 0
    assert bytes_accounted[0] == file_size
    # nothing credited -> no updates recorded
    assert prog_bar.updates == []


# --- helper raisers for monkeypatch tests ---


def _import_error_raiser() -> None:
    msg = "mock import error"
    raise ImportError(msg)


def _os_error_raiser() -> None:
    msg = "mock os error"
    raise OSError(msg)


def _package_not_found_raiser(pkg: str) -> None:
    raise importlib.metadata.PackageNotFoundError(pkg)


# --- into_human_bool edge cases ---


def test_into_human_bool_none() -> None:
    """into_human_bool(None) returns False (non-str/int/bool fallback)."""
    assert utils.into_human_bool(None) is False  # type: ignore[arg-type]


def test_into_human_bool_int_edge() -> None:
    """into_human_bool with int values works correctly."""
    assert utils.into_human_bool(0) is False
    assert utils.into_human_bool(1) is True


def test_into_human_bool_str_t() -> None:
    """into_human_bool with string 't' is truthy."""
    assert utils.into_human_bool("t") is True


# --- is_running_in_notebook ---


def test_is_running_in_notebook_returns_false_when_not_notebook(
    monkeypatch,
) -> None:
    """Non-notebook environment returns False (not ZMQInteractiveShell)."""
    mock_ipython = types.ModuleType("IPython")
    mock_ipython.get_ipython = lambda: None
    monkeypatch.setitem(sys.modules, "IPython", mock_ipython)
    assert utils.is_running_in_notebook() is False


# --- _get_default_log_path ---


def test_get_default_log_path_fallback_import_error(monkeypatch) -> None:
    """_get_default_log_path falls back to tempdir on ImportError from xdg."""
    monkeypatch.setattr("spectrumx.utils.xdg_state_home", _import_error_raiser)
    path = utils._get_default_log_path()
    assert "spectrumx_sdk.jsonl" in str(path)
    assert str(Path(tempfile.gettempdir())) in str(path)


def test_get_default_log_path_fallback_os_error(monkeypatch) -> None:
    """_get_default_log_path falls back to tempdir on OSError from xdg_state_home."""
    monkeypatch.setattr("spectrumx.utils.xdg_state_home", _os_error_raiser)
    path = utils._get_default_log_path()
    assert "spectrumx_sdk.jsonl" in str(path)
    assert str(Path(tempfile.gettempdir())) in str(path)


# --- _emit_boot_message ---


def test_emit_boot_message_package_not_found(monkeypatch, tmp_path) -> None:
    """_emit_boot_message handles PackageNotFoundError gracefully."""
    monkeypatch.setattr(
        "importlib.metadata.version",
        _package_not_found_raiser,
    )
    log_path = tmp_path / "boot_test.jsonl"
    utils._emit_boot_message(log_path)
    assert log_path.exists()
    content = log_path.read_text()
    assert "unknown" in content


def test_emit_boot_message_os_error(tmp_path) -> None:
    """_emit_boot_message handles OSError during write gracefully."""
    utils._emit_boot_message(tmp_path)
    # Should not raise — OSError caught internally


# --- _structured_log_sink ---


def test_structured_log_sink_no_current_path() -> None:
    """_structured_log_sink returns early when _current_log_path is None."""
    utils.reset_structured_logging()
    sink_id = log.add(
        utils._structured_log_sink,
        format="{message}",
        filter=lambda r: True,
    )
    try:
        log.info("this should not raise")
        # The sink returns immediately because _current_log_path is None
    finally:
        log.remove(sink_id)
    utils.reset_structured_logging()


def test_structured_log_sink_os_error(monkeypatch, tmp_path) -> None:
    """_structured_log_sink handles OSError during write gracefully."""
    utils.reset_structured_logging()
    # Set _current_log_path to a directory so open("a") raises IsADirectoryError
    monkeypatch.setattr("spectrumx.utils._current_log_path", tmp_path)
    sink_id = log.add(
        utils._structured_log_sink,
        format="{message}",
        filter=lambda r: True,
    )
    try:
        log.info("this write should trigger OSError and be caught")
    finally:
        log.remove(sink_id)
    utils.reset_structured_logging()


# --- reset_structured_logging ---


def test_reset_structured_logging_clears_state() -> None:
    """reset_structured_logging removes sink and clears all context."""
    utils.reset_structured_logging()
    utils.enable_structured_logging()
    assert utils._structured_sink_id is not None

    utils.set_persistent_log_context(test_key="test_value")
    assert utils._persistent_context == {"test_key": "test_value"}

    utils.reset_structured_logging()

    assert utils._structured_sink_id is None
    assert utils._current_log_path is None
    assert utils._persistent_context == {}
    assert utils._log_context.get() is None


# --- get_random_line ---


@pytest.mark.parametrize(
    "length", [0, 1, 10, 100], ids=["zero", "one", "ten", "hundred"]
)
def test_get_random_line_length(length: int) -> None:
    """get_random_line returns a string of the requested length."""
    assert len(utils.get_random_line(length)) == length


def test_get_random_line_negative_length_returns_empty() -> None:
    """A negative length wraps to an empty string (range(-1) yields no items)."""
    assert utils.get_random_line(-1) == ""


def test_get_random_line_without_punctuation() -> None:
    """get_random_line with include_punctuation=False returns only alphanumeric."""
    result = utils.get_random_line(200, include_punctuation=False)
    assert len(result) == 200
    assert all(c.isalnum() for c in result)


def test_get_random_line_with_punctuation() -> None:
    """get_random_line with include_punctuation=True includes punctuation."""
    result = utils.get_random_line(200, include_punctuation=True)
    assert len(result) == 200
    assert any(not c.isalnum() for c in result)


# --- get_prog_bar ---


def test_get_prog_bar_is_tqdm_instance(monkeypatch) -> None:
    """get_prog_bar returns a tqdm instance."""
    monkeypatch.setattr("spectrumx.utils.is_running_in_notebook", lambda: False)
    bar = utils.get_prog_bar(total=100)
    try:
        assert isinstance(bar, tqdm)
    finally:
        bar.close()


def test_get_prog_bar_ncols_non_notebook(monkeypatch) -> None:
    """get_prog_bar uses ncols=120 in non-notebook environments."""
    monkeypatch.setattr("spectrumx.utils.is_running_in_notebook", lambda: False)
    bar = utils.get_prog_bar(total=100)
    try:
        assert bar.ncols == 120
    finally:
        bar.close()
