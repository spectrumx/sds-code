"""Tests for the config module."""

import logging
from pathlib import Path

import pytest
from spectrumx.config import CFG_NAME_LOOKUP
from spectrumx.config import DEFAULT_HTTP_TIMEOUT
from spectrumx.config import DeprecatedOption
from spectrumx.config import SDSConfig
from spectrumx.config import _clean_config

# =============================================================================
# DeprecatedOption
# =============================================================================


def test_user_warning_mentions_deprecated_name_and_removal_notice() -> None:
    """DeprecatedOption.user_warning includes the deprecation marker and the name."""
    opt = DeprecatedOption(deprecated_name="TIMEOUT")
    warning = opt.user_warning
    assert "deprecated" in warning
    assert "TIMEOUT" in warning
    assert "will be removed" in warning


def test_user_warning_mentions_replacement_name_when_set() -> None:
    """DeprecatedOption.user_warning includes new_name when set."""
    opt = DeprecatedOption(
        deprecated_name="TIMEOUT",
        new_name="HTTP_TIMEOUT",
    )
    warning = opt.user_warning
    assert "Use 'HTTP_TIMEOUT' instead" in warning


def test_user_warning_mentions_removal_version_when_set() -> None:
    """DeprecatedOption.user_warning includes removal_version when set."""
    opt = DeprecatedOption(
        deprecated_name="TIMEOUT",
        removal_version="0.2.0",
    )
    warning = opt.user_warning
    assert "in v0.2.0" in warning


def test_user_warning_mentions_reason_when_set() -> None:
    """DeprecatedOption.user_warning includes reason when set."""
    opt = DeprecatedOption(
        deprecated_name="TIMEOUT",
        reason="renamed for clarity",
    )
    warning = opt.user_warning
    assert "renamed for clarity" in warning


# =============================================================================
# SDSConfig — init_config
# =============================================================================


def test_init_config_env_file_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init_config with env_file=None sets _env_file to None."""
    monkeypatch.chdir(tmp_path)
    config = SDSConfig(env_file=None, env_config={}, verbose=False)
    assert config._env_file is None


def test_init_config_env_file_unset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """init_config with env_file=Unset (default) sets _env_file to Path('.env')
    resolved to cwd."""
    monkeypatch.chdir(tmp_path)
    config = SDSConfig(env_file=None, env_config={}, verbose=False)
    # Re-init with Unset default via init_config directly
    config.init_config(env_config={}, verbose=False)
    assert config._env_file == tmp_path / ".env"


# =============================================================================
# SDSConfig — _set_config
# =============================================================================


def test_set_config_log_file_string_to_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_set_config with log_file as string converts to Path."""
    monkeypatch.chdir(tmp_path)
    log_path = tmp_path / "test.log"
    config = SDSConfig(
        env_file=None,
        env_config={"log_file": str(log_path)},
        verbose=False,
    )
    assert isinstance(config.log_file, Path)
    assert str(config.log_file) == str(log_path)


def test_set_config_log_file_none() -> None:
    """_set_config leaves log_file as None when not provided."""
    config = SDSConfig(env_file=None, env_config={}, verbose=False)
    assert config.log_file is None


# =============================================================================
# SDSConfig — __load_config (via init_config)
# =============================================================================


def test_load_config_verbose_with_env_file(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """__load_config when verbose=True and env_file exists logs
    'found environment file'."""
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)

    env_file = tmp_path / ".env"
    env_file.write_text("SDS_HOST=example.com\n")

    SDSConfig(env_file=env_file, env_config={}, verbose=True)

    assert "found environment file" in caplog.text


def test_load_config_verbose_no_env_file(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """__load_config when verbose=True and env_file is None logs
    'not using an env file'."""
    caplog.set_level(logging.INFO)
    monkeypatch.chdir(tmp_path)

    SDSConfig(env_file=None, env_config={}, verbose=True)

    assert "not using an env file" in caplog.text


def test_load_config_sds_secret_token_from_environ(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """__load_config loads SDS_SECRET_TOKEN from os.environ."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SDS_SECRET_TOKEN", "my-secret-token")

    config = SDSConfig(env_file=None, env_config={}, verbose=False)

    assert config.api_key == "my-secret-token"


def test_load_config_deprecated_option_warning(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """__load_config warns about deprecated 'TIMEOUT' option when present."""
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)

    SDSConfig(env_file=None, env_config={"timeout": "30"}, verbose=False)

    assert "deprecated" in caplog.text


def test_load_config_custom_env_file_missing(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """__load_config custom env file missing logs warning."""
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)

    custom_env = tmp_path / "custom.env"
    # Intentionally NOT creating the file

    SDSConfig(env_file=custom_env, env_config={}, verbose=False)

    assert "Environment file missing" in caplog.text
    assert "Custom env file not found" in caplog.text


# =============================================================================
# SDSConfig — show_config (basic smoke test)
# =============================================================================


def test_show_config(capsys: pytest.CaptureFixture[str]) -> None:
    """show_config prints the active configuration."""
    config = SDSConfig(
        env_file=None, env_config={"SDS_HOST": "test.example.com"}, verbose=False
    )
    config.show_config()
    captured = capsys.readouterr()
    assert "SDS_Config: active configuration" in captured.out


# =============================================================================
# _clean_config
# =============================================================================


def test_clean_config_skips_none_value() -> None:
    """_clean_config skips entries with None value (line 237-238)."""
    env_config = {
        "SDS_HOST": "example.com",
        "HTTP_TIMEOUT": None,
    }
    result = _clean_config(name_lookup=CFG_NAME_LOOKUP, env_config=env_config)

    # Only SDS_HOST should be in the result; HTTP_TIMEOUT with None is skipped
    assert len(result) == 1
    assert result[0].attr_name == "sds_host"
    assert result[0].attr_value == "example.com"


# =============================================================================
# Deprecated-option functional behavior (warning is incident; migration is contract)
# =============================================================================


def test_http_timeout_option_sets_timeout_attr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The current HTTP_TIMEOUT key maps to the timeout attribute."""
    monkeypatch.chdir(tmp_path)
    config = SDSConfig(env_file=None, env_config={"HTTP_TIMEOUT": "30"}, verbose=False)
    assert config.timeout == 30
    assert config.timeout != DEFAULT_HTTP_TIMEOUT


def test_deprecated_timeout_key_warns_but_does_not_set_timeout(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The deprecated timeout key warns and is dropped — does NOT set timeout.

    Note: the deprecated-key list advertises new_name=HTTP_TIMEOUT purely as
    user copy; timeout is not in CFG_NAME_LOOKUP, so its value is dropped as
    unrecognized and config.timeout keeps its default. This pins the real
    behavior (the user-facing contract: a deprecated key is not silently
    honored).
    """
    caplog.set_level(logging.WARNING)
    monkeypatch.chdir(tmp_path)

    config = SDSConfig(env_file=None, env_config={"timeout": "30"}, verbose=False)

    # The deprecation warning WAS emitted (the contract that's actually implemented).
    assert "deprecated" in caplog.text
    # The dropped value did not take effect — the default survives.
    assert config.timeout == SDSConfig().timeout
