"""SDS Client configuration."""

import logging
import os
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dotenv
from loguru import logger as log

from spectrumx.errors import Unset

from .models import SDSModel
from .utils import into_human_bool
from .utils import log_user
from .utils import log_user_warning

SDSModelT = type[SDSModel]
AttrValueT = str | int | float | bool
logger = logging.getLogger(__name__)


@dataclass
class Attr:
    """Attribute for the SDS configuration."""

    attr_name: str
    attr_value: AttrValueT | None = None
    cast_fn: Callable[[str], AttrValueT] | None = None


# '_cfg_name_lookup' maps config names to attribute names (internal).
#   This allows decoupling env file names from attribute
#   names in the object; used for refactoring code without
#   breaking user configuration files. Use lower case.
_cfg_name_lookup = {
    "dry_run": Attr(attr_name="dry_run", cast_fn=into_human_bool),
    "http_timeout": Attr(attr_name="http_timeout", cast_fn=int),
    "sds_host": Attr(attr_name="sds_host"),
    "sds_secret_token": Attr(attr_name="api_key"),
}


@dataclass
class DeprecatedOption:
    """Deprecated option for the SDS configuration."""

    deprecated_name: str
    new_name: str | None = None
    deprecation_version: str | None = None
    removal_version: str | None = None
    reason: str | None = None
    _user_warning: str | None = None

    @property
    def user_warning(self) -> str:
        """Gets the user warning."""
        warning = ""
        warning += f"Option '{self.deprecated_name}' is deprecated and will be removed"
        warning += f" in v{self.removal_version}." if self.removal_version else "."
        warning += f" Use '{self.new_name}' instead." if self.new_name else ""
        warning += f" {self.reason}" if self.reason else ""
        return warning


class SDSConfig:
    """Configuration for the SpectrumX Data System."""

    sds_host: None | str = None
    api_key: str = ""
    dry_run: bool = True  # safer default
    timeout: int = 30

    _active_config: list[Attr]
    _env_file: Path | None = None

    def __init__(
        self,
        *,
        env_file: Path | None = None,
        env_config: Mapping[str, Any] | None = None,
        sds_host: None | str = None,
        verbose: bool = False,
    ) -> None:
        """Initialize the configuration.
        Args:
            env_file:   Path to the environment file to load the config from.
            env_config: Overrides for the environment file.
            sds_host:   The host to connect to (the config file has priority over this).
            verbose:    Show which config files are loaded and which attributes are set.
        """
        self.sds_host = sds_host
        self.init_config(env_file=env_file, env_config=env_config, verbose=verbose)

    def init_config(
        self,
        *,
        env_file: Path | None | type[Unset] = Unset,
        env_config: Mapping[str, Any] | None,
        verbose: bool,
    ) -> None:
        """Initializes the client config, with `env_config` taking precedence.

        Args:
            env_file:   Path to the environment file to load the config from.
            env_config: Overrides for the environment file.
            verbose:    Show which config files are loaded and which attributes are set.

        """
        base_dir = Path.cwd()
        if env_file is Unset:
            self._env_file = Path(".env")
        elif isinstance(env_file, (str, Path)):
            self._env_file = Path(env_file)
        else:
            self._env_file = None
        if self._env_file and not self._env_file.is_absolute():
            self._env_file = base_dir / self._env_file
        clean_config = self.__load_config(env_cli_config=env_config, verbose=verbose)
        self._set_config(clean_config)

    def show_config(self, log_fn: Callable[[str], None] = print) -> None:
        """Show the active configuration."""
        header = "SDS_Config: active configuration:"
        log.debug(header)  # for sdk developers
        log_fn(header)  # for users
        for attr in self._active_config:
            _log_redacted(
                key=attr.attr_name,
                value=str(attr.attr_value),
                log_fn=log_fn,
            )

    def _set_config(self, clean_config: list[Attr]) -> None:
        """Sets the instance attributes."""
        for attr in clean_config:
            setattr(
                self,
                attr.attr_name,
                attr.value,
            )
            _log_redacted(key=attr.attr_name, value=attr.value)

        # validate attributes / show user warnings
        if not self.api_key:
            log.error(
                "SDS_Config: API key not set. Check your environment"
                " file has an SDS_SECRET_TOKEN set."
            )

        self._active_config = clean_config

    def __load_config(
        self,
        *,
        env_cli_config: Mapping[str, Any] | None = None,
        verbose: bool = False,
    ) -> list[Attr]:
        """Load the configuration."""
        if self._env_file and not self._env_file.exists():
            msg = f"Environment file missing: {self._env_file}"
            log_user_warning(msg)

        if verbose:
            if self._env_file:
                msg = f"SDS_Config: found environment file: {self._env_file}"
                log_user(msg)
            else:
                log_user("SDS_Config: not using an env file")

        # get variables from running env
        env_vars = {}
        if secret := os.environ.get("SDS_SECRET_TOKEN"):
            env_vars["SDS_SECRET_TOKEN"] = secret
        env_vars = {k: v for k, v in env_vars.items() if v is not None}
        log.debug(f"SDS_Config: from local env: {list(env_vars.keys())}")

        # merge file, cli, and env vars configs
        if (
            self._env_file
            and not self._env_file.exists()
            and self._env_file.name != ".env"
        ):
            log_user_warning(f"Custom env file not found: {self._env_file}")
        env_file_config = dotenv.dotenv_values(self._env_file, verbose=verbose)
        env_cli_config = env_cli_config or {}
        env_config = {**env_file_config, **env_cli_config, **env_vars}

        # clean and set the configuration loaded
        cleaned_config: list[Attr] = _clean_config(
            name_lookup=_cfg_name_lookup, env_config=env_config
        )

        # `deprecated_names` allows gracefully phasing out settings in future SDK
        # releases. Names are case-insensitive, but listed as uppercase for warnings
        # After `removal_version` is released, its entry may be removed from this list.
        deprecated_opts: list[DeprecatedOption] = [
            DeprecatedOption(
                deprecated_name="TIMEOUT",
                new_name="HTTP_TIMEOUT",
                deprecation_version="0.1.2",
                removal_version="0.2.0",
            ),
        ]
        # warn about deprecated options when found
        for dep_opt in deprecated_opts:
            if dep_opt.deprecated_name.lower() in env_config:
                log_user_warning(dep_opt.user_warning)

        return cleaned_config


def _clean_config(
    name_lookup: dict[str, Attr],
    env_config: Mapping[str, Any],
) -> list[Attr]:
    """Cleans the configuration to match known attributes."""
    cleaned_config: list[Attr] = []
    for key, sensitive_value in env_config.items():
        normalized_key: str = key.lower().replace("-", "_").replace(" ", "_")

        # skip if no value
        if sensitive_value is None:
            log.warning(f"SDS_Config: {key} has no value")
            continue
        attr: Attr | None = name_lookup.get(normalized_key)

        # warn of invalid config
        if attr is None:
            msg = f"SDS_Config: {key} not recognized"
            log.warning(msg)
            logger.warning(msg)
            continue

        # set value
        attr.value = attr.cast_fn(sensitive_value) if attr.cast_fn else sensitive_value

        # set the attribute, casting if necessary
        cleaned_config.append(attr)

    return cleaned_config


def _log_redacted(
    key: str,
    value: str,
    log_fn: Callable[[str], None] = logger.info,
    depth: int = 1,
) -> None:
    """Logs but redacts value if the key hints to a sensitive content, as passwords."""
    std_length: int = 4
    lower_case_hints = {
        "key",
        "secret",
        "token",
        "pass",
    }
    safe_value = (
        "*" * std_length
        if any(hint in key.lower() for hint in lower_case_hints)
        else value
    )
    del value
    msg = f"\tSDS_Config: set {key}={safe_value}"
    log.opt(depth=depth).debug(msg)  # for sdk developers
    log_fn(msg)


__all__ = ["SDSConfig"]
