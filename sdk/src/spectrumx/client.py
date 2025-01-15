"""Client for the SpectrumX Data System."""

import logging
import os
import uuid
from collections.abc import Callable
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

import dotenv
from loguru import logger as log
from pydantic import UUID4

from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.ops.pagination import Paginator

from . import __version__
from .gateway import GatewayClient
from .models import File
from .models import SDSModel
from .ops import files
from .utils import get_prog_bar
from .utils import into_human_bool
from .utils import log_user
from .utils import log_user_error
from .utils import log_user_warning

if TYPE_CHECKING:
    from tqdm import tqdm

SDSModelT = type[SDSModel]
AttrValueT = str | int | float | bool


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
    _env_file: Path

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
        env_file: Path | None,
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
        self._env_file = Path(env_file) if env_file else Path(".env")
        if not self._env_file.is_absolute():
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
        if not self._env_file.exists():
            msg = f"Environment file missing: {self._env_file}"
            log_user_warning(msg)

        if verbose:
            msg = f"SDS_Config: found environment file: {self._env_file}"
            log_user(msg)

        # get variables from running env
        env_vars = {
            "SDS_SECRET_TOKEN": os.getenv("SDS_SECRET_TOKEN", default=None),
        }
        env_vars = {k: v for k, v in env_vars.items() if v is not None}
        log.debug(f"SDS_Config: from env: {env_vars}")

        # merge file, cli, and env vars configs
        if not self._env_file.exists() and self._env_file.name != ".env":
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


class Client:
    """Instantiates and SDS client."""

    host: str
    is_authenticated: bool
    verbose: bool = False

    _gateway: GatewayClient
    _config: SDSConfig

    def __init__(
        self,
        host: None | str,
        *,
        env_file: Path | None = None,
        env_config: Mapping[str, Any] | None = None,
        verbose: bool = False,
    ) -> None:
        # avoids circular import
        from spectrumx.api import sds_files as _sds_files

        self._sds_files = _sds_files

        self.host = host
        self.is_authenticated = False
        self.verbose = verbose
        self._config = SDSConfig(
            env_file=env_file,
            env_config=env_config,
            sds_host=host,
            verbose=self.verbose,
        )

        # initialize the gateway
        self._gateway = GatewayClient(
            host=self.host,
            api_key=self._config.api_key,
            timeout=self._config.timeout,
            verbose=self.verbose,
        )
        self._issue_user_alerts()

    def __str__(self) -> str:
        return f"Client(host={self.host})"

    def _issue_user_alerts(self) -> None:
        """Logs important messages on initialization."""
        if __version__.startswith("0.1."):
            log_user_warning(
                "This version of the SDK is in early development. "
                "Expect breaking changes in the future."
            )
        if self.dry_run:
            log_user("Dry run enabled: no SDS requests will be made or files written")

    @property
    def dry_run(self) -> bool:
        """When in dry run mode, no SDS requests are made and files are not written."""
        return self._config.dry_run

    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        """Sets the dry run mode."""

        self._config.dry_run = bool(value)
        msg = (
            "Dry-run enabled: no SDS requests will be made or files written."
            if self._config.dry_run
            else "Dry-run DISABLED: modifications are now possible."
        )
        log_user_warning(msg)

    @property
    def base_url(self) -> str:
        """Base URL for the client."""
        return self._gateway.base_url

    @property
    def base_url_no_port(self) -> str:
        """Base URL without the port."""
        return self._gateway.base_url_no_port

    def authenticate(self) -> None:
        """Authenticate the client."""
        if self.dry_run:
            log_user("Dry run is enabled: assuming successful authentication")
            log_user("To authenticate against SDS, set Client.dry_run to False")
        else:
            log.warning("Dry run DISABLED: authenticating")
            self._gateway.authenticate()
        self.is_authenticated = True

    def get_file(self, file_uuid: UUID4 | str) -> File:
        """Get a file instance by its ID. Only metadata is downloaded from SDS.

        Note this does not download the file contents from the server. File
            instances still need to have their contents downloaded to create
            a local copy - see `Client.download_file()`.

        Args:
            file_uuid: The UUID of the file to retrieve.
        Returns:
            The file instance, or a sample file if in dry run mode.
        """

        return self._sds_files.get_file(client=self, file_uuid=file_uuid)

    def download(
        self,
        *,
        from_sds_path: Path | str,
        to_local_path: Path | str,
        skip_contents: bool = False,
        overwrite: bool = False,
        verbose: bool = True,
    ) -> list[Result[File]]:
        """Downloads files from SDS.

        Args:
            from_sds_path:  The virtual directory on SDS to download files from.
            to_local_path:  The local path to save the downloaded files to.
            skip_contents:  When True, only the metadata is downloaded.
            overwrite:      Whether to overwrite existing local files.
            verbose:        Show a progress bar.
        Returns:
            A list of results for each file discovered and downloaded.
        """
        from_sds_path = Path(from_sds_path)
        to_local_path = Path(to_local_path)

        # local vars
        prefix = "Dry-run: simulating download:" if self.dry_run else "Downloading:"

        if not to_local_path.exists():
            if self.dry_run:
                log_user(f"Dry run: would create the directory '{to_local_path}'")
            else:
                to_local_path.mkdir(parents=True)

        if self.dry_run:
            log_user(
                "Called download() in dry run mode: "
                "files are made-up and not written to disk."
            )
            uuids = [uuid.uuid4() for _ in range(10)]
            files_to_download = [files.generate_sample_file(uuid) for uuid in uuids]
            log_user(f"Dry run: discovered {len(files_to_download)} files (samples)")
        else:
            files_to_download = self._gateway.list_files(from_sds_path)
            if verbose:
                log_user(f"Discovered {len(files_to_download)} files")

        prog_bar: tqdm[File] = get_prog_bar(
            files_to_download, desc="Downloading", disable=not verbose
        )

        results: list[Result[File]] = []
        for file_info in prog_bar:
            prog_bar.set_description(f"{prefix} '{file_info.name}'")
            local_file_path = to_local_path / file_info.directory / file_info.name

            # skip download of local files (without UUID)
            if file_info.uuid is None:
                msg = f"Skipping local file: {file_info.name}"
                log_user_warning(msg)
                results.append(Result(exception=SDSError(msg)))
                continue

            # register failure if the resolved path is not relative to the target
            if not local_file_path.is_relative_to(to_local_path):
                msg = (
                    f"Resolved path {local_file_path} is not relative to "
                    f"{to_local_path}: skipping download."
                )
                log_user_warning(msg)
                results.append(Result(exception=SDSError(msg)))
                continue

            # avoid unintended overwrites (success)
            if local_file_path.exists() and not overwrite:
                log_user(f"Skipping existing file: '{local_file_path}'")
                results.append(Result(value=file_info))
                continue

            # download the file and register result
            try:
                self.download_file(
                    file_uuid=file_info.uuid,
                    to_local_path=local_file_path,
                    skip_contents=skip_contents,
                )
                results.append(Result(value=file_info))
            except SDSError as err:
                log_user_error(f"Download failed: {err}")
                results.append(Result(exception=err))

        return results

    def list_files(
        self, sds_path: Path | str, *, verbose: bool = False
    ) -> Paginator[File]:
        """Lists files in a given SDS path.

        Args:
            sds_path: The virtual directory on SDS to list files from.
            verbose:  Show network requests and other info.
        Returns:
            A paginator for the files in the given SDS path.
        """
        return self._sds_files.list_files(
            client=self, sds_path=sds_path, verbose=verbose
        )

    def download_file(
        self,
        *,
        file_instance: File | None = None,
        file_uuid: UUID4 | str | None = None,
        to_local_path: Path | str | None = None,
        skip_contents: bool = False,
        warn_missing_path: bool = True,
    ) -> File:
        """Downloads a file from SDS: metadata and maybe contents.

        Either `file_instance` or `file_uuid` must be provided. When passing
        a `file_instance`, it's recommended to set its `local_path` attribute,
        otherwise the download will create a temporary file on disk.

        Args:
            file_instance:      The file instance to download.
            file_uuid:          The UUID of the file to download.
            to_local_path:      The local path to save the downloaded file to.
            skip_contents:      When True, only the metadata is downloaded
                                    and no files are created on disk.
            warn_missing_path:  Show a warning when the download location is undefined.
        Returns:
            The file instance with updated attributes, or a sample when in dry run.
        """
        return self._sds_files.download_file(
            client=self,
            file_instance=file_instance,
            file_uuid=file_uuid,
            to_local_path=to_local_path,
            skip_contents=skip_contents,
            warn_missing_path=warn_missing_path,
        )

    def upload(
        self,
        *,
        local_path: Path | str,
        sds_path: Path | str = "/",
        verbose: bool = True,
    ) -> list[Result[File]]:
        """Uploads a file or directory to SDS.

        Args:
            local_path: The local path of the file or directory to upload.
            sds_path:   The virtual directory on SDS to upload the file to, \
                            where '/' is the user root.
            verbose:    Show a progress bar.
        """
        local_path = Path(local_path) if isinstance(local_path, str) else local_path
        valid_files = files.get_valid_files(local_path, warn_skipped=True)
        prog_bar = get_prog_bar(valid_files, desc="Uploading", disable=not verbose)
        upload_results: list[Result[File]] = []
        for file_path in prog_bar:
            try:
                result = Result(
                    value=self._sds_files.upload_file(
                        client=self,
                        local_file=file_path,
                        sds_path=sds_path,
                    )
                )
            except SDSError as err:
                log_user_error(f"Upload failed: {err}")
                result = Result(exception=err)
            upload_results.append(result)
        return upload_results

    def upload_file(
        self,
        *,
        local_file: File | Path | str,
        sds_path: Path | str = "/",
    ) -> File:
        """Uploads a file to SDS.

        If the file instance passed already has a directory set, `sds_path` will
        be prepended. E.g. given:
            `sds_path = 'baz'`; and
            `local_file.directory = 'foo/bar/'`, then:
        The file will be uploaded to `baz/foo/bar/` (under the user root in SDS) and
            the returned file instance will have its `directory` attribute updated
            to match this new path.

        Args:
            local_file:     The local file to upload.
            sds_path:       The virtual directory on SDS to upload the file to.
        Returns:
            The file instance with updated attributes, or a sample when in dry run.
        """

        return self._sds_files.upload_file(
            client=self,
            local_file=local_file,
            sds_path=sds_path,
        )


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
            logging.warning(msg)
            continue

        # set value
        attr.value = attr.cast_fn(sensitive_value) if attr.cast_fn else sensitive_value

        # set the attribute, casting if necessary
        cleaned_config.append(attr)

    return cleaned_config


def _log_redacted(
    key: str,
    value: str,
    log_fn: Callable[[str], None] = logging.info,
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
    log.debug(msg)  # for sdk developers
    log_fn(msg)


__all__ = ["Client"]
