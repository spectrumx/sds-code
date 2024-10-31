"""Client for the SpectrumX Data System."""

import logging
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import dotenv
from loguru import logger as log

from spectrumx.models import File
from spectrumx.models import SDSModel

from .gateway import GatewayClient

SDSModelT = type[SDSModel]
AttrValueT = str | int | float | bool


@dataclass
class Attr:
    """Attribute for the SDS configuration."""

    attr_name: str
    attr_value: AttrValueT | None = None
    cast_fn: Callable[[str], AttrValueT] | None = None


class SDSConfig:
    """Configuration for the SpectrumX Data System."""

    api_key: str = ""
    timeout: int = 30
    _env_file: Path
    _active_config: list[Attr]

    def __init__(
        self,
        *,
        env_file: Path | None = None,
        env_config: Mapping[str, Any] | None = None,
        verbose: bool = False,
    ) -> None:
        """Initialize the configuration.
        Args:
            env_file:   Path to the environment file.
            env_config: Configuration from the CLI.
            verbose:    Show which config files are loaded and which attributes are set.
        """
        base_dir = Path.cwd()
        self._env_file = Path(env_file) if env_file else Path(".env")
        if not self._env_file.is_absolute():
            self._env_file = base_dir / self._env_file
        self._active_config = self._load_config(
            env_cli_config=env_config, verbose=verbose
        )

    def show_config(self, log_fn: Callable[[str], None] = print) -> None:
        """Show the active configuration."""
        header = "SDS_Config: active configuration:"
        log.debug(header)  # for sdk developers
        log_fn(header)  # for users
        for attr in self._active_config:
            log_redacted(attr.attr_name, str(attr.attr_value), log_fn=log_fn)

    def _load_config(
        self,
        *,
        env_cli_config: Mapping[str, Any] | None = None,
        verbose: bool = False,
    ) -> list[Attr]:
        """Load the configuration."""
        if not self._env_file.exists():
            msg = f"Environment file missing: {self._env_file}"
            log.warning(msg)  # for sdk developers
            logging.warning(msg)  # for users
            return []

        if verbose:
            msg = f"SDS_Config: found environment file: {self._env_file}"
            log.debug(msg)  # for sdk developers
            logging.debug(msg)  # for users

        # 'name_lookup' allows decoupling for env file names and
        #   object attribute names for refactoring code; use lower case.
        name_lookup = {
            "sds_secret_token": Attr(attr_name="api_key"),
            "http_timeout": Attr(attr_name="timeout", cast_fn=int),
        }

        # merge file and cli configs
        env_file_config = dotenv.dotenv_values(self._env_file, verbose=verbose)
        env_cli_config = env_cli_config or {}
        env_config = {**env_file_config, **env_cli_config}

        # clean and set the configuration loaded
        cleaned_config: list[Attr] = clean_config(name_lookup, env_config)
        for attr in cleaned_config:
            setattr(
                self,
                attr.attr_name,
                attr.value,
            )
            log_redacted(attr.attr_name, attr.value)

        # validate attributes / show user warnings
        if not self.api_key:
            log.error(
                "SDS_Config: API key not set. Check your environment"
                " file has an SDS_SECRET_TOKEN set."
            )

        return cleaned_config


def log_redacted(
    key: str,
    value: str,
    log_fn: Callable[[str], None] = logging.info,
) -> None:
    """Redacts the value if the key looks sensitive."""
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
    log.debug(msg)  # for sdk developers
    log_fn(msg)


class Client:
    """Instantiates and SDS client."""

    host: str
    is_authenticated: bool
    _gateway: GatewayClient
    _config: SDSConfig

    def __init__(
        self,
        host: str,
        *,
        env_file: Path | None = None,
        env_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.host = host
        self.is_authenticated = False
        self._config = SDSConfig(env_file=env_file, env_config=env_config)
        self._gateway = GatewayClient(
            host=self.host,
            api_key=self._config.api_key,
            timeout=self._config.timeout,
        )

    @property
    def base_url(self) -> str:
        """Base URL for the client."""
        return self._gateway.base_url

    def authenticate(self) -> None:
        """Authenticate the client."""
        self._gateway.authenticate()
        self.is_authenticated = True

    def get_file(self, file_id: str) -> File:
        """Get a file by its ID."""
        response = self._gateway.get_file_by_id(uuid=file_id)
        return File.model_validate_json(response)

    def __str__(self) -> str:
        return f"Client(host={self.host})"


def clean_config(name_lookup, env_config) -> list[Attr]:
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
            logging.warning(msg)
            continue

        # set value
        attr.value = attr.cast_fn(sensitive_value) if attr.cast_fn else sensitive_value

        # set the attribute, casting if necessary
        cleaned_config.append(attr)

    return cleaned_config


__all__ = ["Client"]
