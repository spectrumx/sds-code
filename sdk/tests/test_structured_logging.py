"""Tests for structured logging functionality."""

import json
from pathlib import Path

import pytest
from loguru import logger as log
from spectrumx import utils
from spectrumx.utils import LOG_CATEGORY_LOG
from spectrumx.utils import LogContext
from spectrumx.utils import enable_structured_logging
from spectrumx.utils import reset_structured_logging
from spectrumx.utils import set_persistent_log_context

MIN_LOG_LINES = 2


@pytest.fixture(autouse=True)
def reset_logging_state():
    """Reset structured logging state before and after each test."""
    reset_structured_logging()
    yield
    reset_structured_logging()


def test_jsonl_file_creation_default_xdg_path(tmp_path: Path, monkeypatch) -> None:
    """Test JSONL file creation at default XDG path."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg_state"))

    enable_structured_logging()
    log.info("test message for default path")

    current_log_path = utils._current_log_path  # noqa: SLF001
    assert current_log_path is not None
    assert current_log_path.exists()
    assert current_log_path.suffix == ".jsonl"
    assert "spectrumx" in current_log_path.parts
    assert "logs" in current_log_path.parts


def test_jsonl_file_creation_custom_path(tmp_path: Path) -> None:
    """Test JSONL file creation at custom path."""
    custom_path = tmp_path / "custom" / "my_log.jsonl"

    enable_structured_logging(log_path=custom_path)
    log.info("test message for custom path")

    current_log_path = utils._current_log_path  # noqa: SLF001
    assert current_log_path == custom_path
    assert custom_path.exists()
    lines = custom_path.read_text().strip().split("\n")
    assert len(lines) >= 1
    entry = json.loads(lines[-1])
    assert entry["msg"] == "test message for custom path"


def test_boot_message_emission(tmp_path: Path) -> None:
    """Test boot message is emitted every time structured logging is enabled."""
    log_file = tmp_path / "boot_test.jsonl"

    enable_structured_logging(log_path=log_file)
    log.info("trigger boot message")

    lines = log_file.read_text().strip().split("\n")
    assert len(lines) >= MIN_LOG_LINES  # boot message + at least one log line

    boot_entry = json.loads(lines[0])
    assert boot_entry["msg"] == "system info"
    assert boot_entry["lvl"] == "INFO"
    assert boot_entry["cat"] == LOG_CATEGORY_LOG
    assert "sdk_version" in boot_entry
    assert "os" in boot_entry
    assert "python" in boot_entry
    assert "log_file" in boot_entry


def test_core_fields_present_on_every_log_line(tmp_path: Path) -> None:
    """Test core fields (ts, pid, lvl, cat, msg) present on every log line."""
    log_file = tmp_path / "core_fields.jsonl"

    enable_structured_logging(log_path=log_file)
    log.info("core fields test")
    log.warning("another core fields test")

    lines = log_file.read_text().strip().split("\n")
    # First line is boot message, rest are log lines
    for line in lines[1:]:
        entry = json.loads(line)
        assert "ts" in entry
        assert "pid" in entry
        assert "lvl" in entry
        assert "cat" in entry
        assert "msg" in entry


def test_contextual_fields_only_when_set(tmp_path: Path) -> None:
    """Test contextual fields only present when explicitly set."""
    log_file = tmp_path / "contextual_fields.jsonl"

    enable_structured_logging(log_path=log_file)

    # Without any context set
    log.info("no context")

    # With persistent context set
    set_persistent_log_context(api_key_prefix="test_key", timeout=120)
    log.info("with persistent context")

    # With scoped context
    with LogContext(upload_id="abc123", upload_dir="/some/dir"):
        log.info("with scoped context")

    lines = log_file.read_text().strip().split("\n")
    # lines[0] = boot, lines[1] = no context, lines[2] = persistent, lines[3] = scoped
    no_ctx_entry = json.loads(lines[1])
    persistent_entry = json.loads(lines[2])
    scoped_entry = json.loads(lines[3])

    # No context line: no upload_id, no upload_dir, no api_key_prefix
    assert "upload_id" not in no_ctx_entry
    assert "upload_dir" not in no_ctx_entry
    assert "api_key_prefix" not in no_ctx_entry

    # Persistent context line: has api_key_prefix and timeout
    assert persistent_entry.get("api_key_prefix") == "test_key"
    assert persistent_entry.get("timeout") == 120  # noqa: PLR2004

    # Scoped context line: has upload_id and upload_dir
    assert scoped_entry.get("upload_id") == "abc123"
    assert scoped_entry.get("upload_dir") == "/some/dir"
    # Also has persistent context
    assert scoped_entry.get("api_key_prefix") == "test_key"


def test_category_binding_via_log_bind(tmp_path: Path) -> None:
    """Test category binding via log.bind()."""
    log_file = tmp_path / "category_bind.jsonl"

    enable_structured_logging(log_path=log_file)
    log.bind(cat="network").info("network message")
    log.bind(cat="auth").warning("auth message")
    log.info("default category message")  # no bind -> default "log"

    lines = log_file.read_text().strip().split("\n")
    network_entry = json.loads(lines[1])
    auth_entry = json.loads(lines[2])
    default_entry = json.loads(lines[3])

    assert network_entry["cat"] == "network"
    assert auth_entry["cat"] == "auth"
    assert default_entry["cat"] == LOG_CATEGORY_LOG


def test_scoped_context_cleared_on_exit(tmp_path: Path) -> None:
    """Test scoped context is cleared on exit (no leakage between operations)."""
    log_file = tmp_path / "scoped_clear.jsonl"

    enable_structured_logging(log_path=log_file)

    with LogContext(upload_id="scoped-id-1"):
        log.info("inside scope 1")

    # After scope exit, upload_id should not leak
    log.info("outside scope")

    lines = log_file.read_text().strip().split("\n")
    inside_entry = json.loads(lines[1])
    outside_entry = json.loads(lines[2])

    assert inside_entry.get("upload_id") == "scoped-id-1"
    assert "upload_id" not in outside_entry


def test_persistent_context_persists(tmp_path: Path) -> None:
    """Test persistent context persists across operations."""
    log_file = tmp_path / "persistent_ctx.jsonl"

    enable_structured_logging(log_path=log_file)
    set_persistent_log_context(api_key_prefix="persist_key", timeout=999)

    log.info("msg 1")
    log.warning("msg 2")

    lines = log_file.read_text().strip().split("\n")
    msg1 = json.loads(lines[1])
    msg2 = json.loads(lines[2])

    assert msg1.get("api_key_prefix") == "persist_key"
    assert msg1.get("timeout") == 999  # noqa: PLR2004
    assert msg2.get("api_key_prefix") == "persist_key"
    assert msg2.get("timeout") == 999  # noqa: PLR2004


def test_enable_structured_logging_override_changes_path(tmp_path: Path) -> None:
    """Test calling enable_structured_logging again changes the log path."""
    path_a = tmp_path / "log_a.jsonl"
    path_b = tmp_path / "log_b.jsonl"

    enable_structured_logging(log_path=path_a)
    log.info("written to path A")

    assert utils._current_log_path == path_a  # noqa: SLF001
    assert path_a.exists()

    # Re-enable with new path — boot message emitted again on new file
    enable_structured_logging(log_path=path_b)
    log.info("written to path B")

    assert utils._current_log_path == path_b  # noqa: SLF001
    assert path_b.exists()

    # Path A should not have the second message
    lines_a = path_a.read_text().strip().split("\n")
    log_entries_a = [json.loads(line) for line in lines_a]
    msgs_a = [e["msg"] for e in log_entries_a if e["msg"] != "system info"]
    assert "written to path B" not in msgs_a

    # Path B should have the second message and its own boot message
    lines_b = path_b.read_text().strip().split("\n")
    boot_b = json.loads(lines_b[0])
    assert boot_b["msg"] == "system info"
    msgs_b = [json.loads(line)["msg"] for line in lines_b]
    assert "written to path B" in msgs_b


def test_reset_structured_logging_clears_state() -> None:
    """Test reset_structured_logging clears all state."""
    enable_structured_logging()
    set_persistent_log_context(api_key_prefix="should_be_cleared")

    with LogContext(upload_id="should_be_cleared"):
        pass

    reset_structured_logging()

    assert utils._structured_sink_id is None  # noqa: SLF001
    assert utils._current_log_path is None  # noqa: SLF001
    assert utils._persistent_context == {}  # noqa: SLF001
    assert utils._log_context.get() is None  # noqa: SLF001
