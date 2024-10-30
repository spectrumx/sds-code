"""Client for the SpectrumX Data System."""

import logging
from collections.abc import Callable
from pathlib import Path

import dotenv
from loguru import logger as log

from spectrumx.models import File
from spectrumx.models import SDSModel

from .gateway import GatewayClient

SDSModelT = type[SDSModel]


class SDSConfig:
    """Configuration for the SpectrumX Data System."""

    api_key: str = ""
    timeout: int = 30
    _env_file: Path

    def __init__(self, env_file: Path | None = None) -> None:
        base_dir = Path.cwd()
        self._env_file = Path(env_file) if env_file else Path(".env")
        if not self._env_file.is_absolute():
            self._env_file = base_dir / self._env_file
        self._load_config()

    def _load_config(self) -> None:
        """Load the configuration."""
        if not self._env_file.exists():
            msg = f"Environment file not found: {self._env_file}"
            log.warning(msg)  # for sdk developers
            logging.warning(msg)  # for users
            return
        msg = f"SDS_Config: loading environment file: {self._env_file}"
        log.debug(msg)

        for key, sensitive_value in dotenv.dotenv_values(self._env_file).items():
            normalized_key: str = key.lower().replace("-", "_").replace(" ", "_")
            # cast to the expected type
            if sensitive_value is None:
                log.warning(f"SDS_Config: {key} has no value")
                continue
            if normalized_key in {"timeout"}:
                setattr(self, normalized_key, int(sensitive_value))
            else:
                setattr(self, normalized_key, sensitive_value)
            log_redacted(key, sensitive_value)
        if not self.api_key:
            log.error("SDS_Config: API key not set. Check your environment file.")


def log_redacted(
    key: str,
    value: str,
    log_fn: Callable[[str], None] = log.debug,
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
    log_fn(f"\tSDS_Config: setting {key}={safe_value}")


class Client:
    """Instantiates and SDS client."""

    host: str
    is_authenticated: bool
    _gateway: GatewayClient
    _config: SDSConfig

    def __init__(self, host: str, env_file: Path | None = None) -> None:
        self.host = host
        self.is_authenticated = False
        self._config = SDSConfig(env_file)
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


__all__ = ["Client"]
