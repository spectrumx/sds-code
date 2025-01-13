"""Client for the SpectrumX Data System."""

import logging
import os
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum, auto
from multiprocessing.synchronize import RLock
from pathlib import Path
from typing import Any, cast

import dotenv
from loguru import logger as log
from pydantic import UUID4

from spectrumx.errors import Result, SDSError

from . import __version__
from .gateway import GatewayClient
from .models import File, SDSModel
from .ops import files
from .utils import (
    get_prog_bar,
    into_human_bool,
    log_user,
    log_user_error,
    log_user_warning,
)

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


class FileUploadMode(Enum):
    """Modes for uploading files to SDS."""

    SKIP = auto()  # no upload or update needed
    UPDATE_METADATA_ONLY = auto()  # no file contents, update an existing file entry
    UPLOAD_CONTENTS_AND_METADATA = auto()  # create a new file uploading everything
    UPLOAD_METADATA_ONLY = auto()  # no file contents, create a new file entry
    # file contents are immutable, so there is no "UPDATE_CONTENTS_ONLY"


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
            host:       The host to connect to (the config file has priority over this).
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
            log_user("Dry run enabled: authenticated")
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

        uuid_to_set: UUID4 = (
            uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
        )

        if not self.dry_run:
            file_bytes = self._gateway.get_file_by_id(uuid=uuid_to_set.hex)
            return File.model_validate_json(file_bytes)

        log_user("Dry run enabled: a sample file is being returned instead")
        return files.generate_sample_file(uuid_to_set)

    def download(
        self,
        *,
        from_sds_path: Path | str,
        to_local_path: Path | str,
        skip_contents: bool = False,
        overwrite: bool = False,
        verbose: bool = True,
    ) -> list[Result]:
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

        prog_bar = get_prog_bar(
            files_to_download, desc="Downloading", disable=not verbose
        )

        results: list[Result] = []
        for file_info in prog_bar:
            file_info = cast(File, file_info)
            prog_bar.set_description(f"{prefix} '{file_info.name}'")
            local_file_path = (
                to_local_path / (os.sep + str(file_info.directory)) / file_info.name
            )

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
        if isinstance(file_instance, File):
            if file_instance.uuid is None:
                msg = "The file passed is a local reference and cannot be downloaded."
                raise ValueError(msg)
            if file_instance.local_path is None and warn_missing_path:
                msg = (
                    "The file instance passed is missing a local path to "
                    "download to. A temporary file will be created on disk."
                )
                log_user_warning(msg)
            if skip_contents:
                msg = (
                    "A file instance was provided and skip_contents "
                    "is True: nothing to download."
                )
                log_user_warning(msg)
                return file_instance
            valid_uuid = file_instance.uuid
            valid_local_path_or_none = file_instance.local_path
        else:
            if file_uuid is None:
                msg = "Expected a file instance or UUID to download."
                raise ValueError(msg)
            if to_local_path is None and warn_missing_path:
                msg = "The file will be downloaded as temporary."
                log_user_warning(msg)

            valid_local_path_or_none = Path(to_local_path) if to_local_path else None

            # download
            valid_uuid: UUID4 = (
                uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
            )
            if self.dry_run:
                time.sleep(0.05)
                return files.generate_sample_file(valid_uuid)

            assert not self.dry_run, "Internal error: expected dry run to be disabled."
            file_bytes = self._gateway.get_file_by_id(uuid=valid_uuid.hex)
            file_instance = File.model_validate_json(file_bytes)

        if not skip_contents:
            downloaded_path = self._download_file_contents(
                file_uuid=valid_uuid,
                target_path=valid_local_path_or_none,
                contents_lock=file_instance._contents_lock,  # pyright: ignore[reportPrivateUsage] # noqa: SLF001
            )
            file_instance.local_path = downloaded_path
        return file_instance

    def _download_file_contents(
        self,
        *,
        file_uuid: UUID4 | str,
        contents_lock: RLock,
        target_path: Path | None = None,
    ) -> Path:
        """Downloads the contents of a file from SDS to a location on disk.

        If target_path is not provided, a temporary file is created.
        When provided, the parent of target_path will be created if it does not exist.

        Args:
            file_uuid:      The UUID of the file to download from SDS.
            target_path:    The local path to save the downloaded file to.
        Returns:
            The local path to the downloaded file.
        """
        if target_path is None:
            file_desc, file_name = tempfile.mkstemp()
            os.close(file_desc)
            target_path = Path(file_name)
        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        uuid_to_set: UUID4 = (
            uuid.UUID(file_uuid) if isinstance(file_uuid, str) else file_uuid
        )
        if not self.dry_run:
            with target_path.open(mode="wb") as file_ptr, contents_lock:
                for chunk in self._gateway.get_file_contents_by_id(
                    uuid=uuid_to_set.hex
                ):
                    file_ptr.write(chunk)
        else:
            log_user(f"Dry run enabled: file would be saved as {target_path}")
        return target_path

    def upload(
        self,
        *,
        local_path: Path | str,
        sds_path: Path | str = "/",
        verbose: bool = True,
    ) -> list[Result]:
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
        upload_results: list[Result] = []
        for file_path in prog_bar:
            try:
                result = Result(
                    value=self.upload_file(file_path=file_path, sds_path=sds_path)
                )
            except SDSError as err:
                log_user_error(f"Upload failed: {err}")
                result = Result(exception=err)
            upload_results.append(result)
        return upload_results

    def upload_file(
        self,
        *,
        file_path: File | Path | str,
        sds_path: Path | str = "/",
    ) -> File:
        """Uploads a file to SDS.

        Args:
            file_path:  The local path of the file to upload.
            sds_dir:    The virtual directory on SDS to upload the file to, \
                        where '/' is the user root.
        Returns:
            The file instance with updated attributes, or a sample when in dry run.
        """
        # validate inputs
        if not isinstance(file_path, (File, Path, str)):
            msg = (
                "file_path must be a Path, str, or "
                f"File instance, not {type(file_path)}"
            )
            raise TypeError(msg)
        file_path = Path(file_path) if isinstance(file_path, str) else file_path
        sds_path = Path(sds_path) if isinstance(sds_path, str) else sds_path

        # construct the file instance
        file_instance = (
            file_path
            if isinstance(file_path, File)
            else files.construct_file(file_path, sds_path=sds_path)
        )

        return self.__upload_file_mux(file_instance)

    def __upload_file_mux(self, file_instance: File) -> File:
        """Uploads a file instance to SDS, choosing the right upload mode."""
        file_path = file_instance.local_path
        # check whether sds already has this file for this user
        upload_mode, asset_id = self.__get_upload_mode_and_asset(
            file_instance=file_instance
        )

        if self.dry_run:
            log_user(f"Dry run enabled: skipping upload of '{file_path}'")
            return file_instance

        match upload_mode:
            case FileUploadMode.SKIP:
                log_user(f"Skipping upload of existing '{file_path}'")
                return file_instance
            case FileUploadMode.UPLOAD_CONTENTS_AND_METADATA:
                log_user(f"Uploading '{file_path}'")
                file_created_response = self._gateway.upload_new_file(
                    file_instance=file_instance
                )
                uploaded_file = File.model_validate_json(file_created_response)
                uploaded_file.local_path = file_instance.local_path
                return uploaded_file
            case FileUploadMode.UPLOAD_METADATA_ONLY:
                log_user(f"Uploading metadata for '{file_path}'")
                if asset_id is None:
                    msg = "Expected an asset ID when uploading metadata only"
                    raise SDSError(msg)
                return self.__upload_new_file_metadata_only(
                    file_instance=file_instance, sibling_uuid=asset_id
                )
            case FileUploadMode.UPDATE_METADATA_ONLY:  # pragma: no cover
                log_user(f"Updating metadata for '{file_path}'")
                assert (
                    asset_id is not None
                ), "Expected an asset ID when updating metadata"
                return self.__update_existing_file_metadata_only(
                    file_instance=file_instance, asset_id=asset_id
                )
            case _:  # pragma: no cover
                msg = f"Unexpected upload mode: {upload_mode}"
                raise SDSError(msg)

    def __update_existing_file_metadata_only(
        self, file_instance: File, asset_id: UUID4 | None
    ) -> File:
        """UPDATES an existing file instance with new metadata.

        ---
            Note: favor use of the safer `__upload_new_file_metadata_only()`,
            which creates a new File entry reusing the contents of a sibling file.
        ---

        Useful when the files is already instantiated in SDS and the file
            contents did not change: only the metadata needs to be updated.

        Args:
            file_instance:  The file instance with new metadata to update.
        Returns:
            The file instance with updated attributes.
        """
        if asset_id is not None:
            file_instance.uuid = asset_id

        if self.dry_run:
            msg = (
                "Dry run enabled: would update metadata "
                f"only for file '{file_instance.uuid}'"
            )
            log_user(msg)
            return file_instance

        assert not self.dry_run, "Internal error: expected dry run to be disabled."
        file_response = self._gateway.update_existing_file_metadata(
            file_instance=file_instance
        )
        return File.model_validate_json(file_response)

    def __upload_new_file_metadata_only(
        self, file_instance: File, sibling_uuid: UUID4
    ) -> File:
        """UPLOADS a new file instance to SDS, skipping the file contents.

        Useful when there are identical files in different locations: only their
            metadata needs to be uploaded to SDS. There must be a sibling file
            with the right contents, under the same user, already in SDS for this
            method to succeed.

        The sibling entry is not modified and doesn't need to exist locally.

        Args:
            file_instance:  The file instance with new metadata.
            sibling_uuid:   The UUID of the file which contents are identical to.
        Returns:
            The file instance with updated attributes.
        """
        if self.dry_run:
            log_user("Dry run enabled: uploading metadata only")
            return file_instance

        assert not self.dry_run, "Internal error: expected dry run to be disabled."
        file_response = self._gateway.upload_new_file_metadata_only(
            file_instance=file_instance, sibling_uuid=sibling_uuid
        )
        return File.model_validate_json(file_response)

    def __get_upload_mode_and_asset(
        self, file_instance: File
    ) -> tuple[FileUploadMode, uuid.UUID | None]:
        """Determines how to upload a file into SDS.

        Args:
            file_instance:  The file instance to get the upload mode for.
        Returns:
            The mode to upload the file in. Modes are:
                FileUploadMode.SKIP
                FileUploadMode.UPLOAD_CONTENTS_AND_METADATA
                FileUploadMode.UPLOAD_METADATA_ONLY
            Asset ID: The asset ID of the file in SDS, if it exists.

        SKIP is used when the file already exists in SDS and no changes are needed.
        UPLOAD_CONTENTS_AND_METADATA is used when the file is new or its contents
            have changed; it will create a new file entry with new contents.
        UPLOAD_METADATA_ONLY is used when the file contents are already in SDS, and
            it will create a new file entry while reusing existing contents from a
            sibling file.
        ---
        UPDATE_METADATA_ONLY is NOT returned here, as it might cause unintended changes.
            For this reason, "update" methods should be explicitly called by UUID.
        ---
        A "File" in SDS has immutable contents, so there is no "UPDATE_CONTENTS_ONLY".
        Note upload_* methods / modes create new assets in SDS, while update_* don't.
        """
        # always assume upload is needed in dry-run, since we can't contact the server
        if self.dry_run:
            return (
                FileUploadMode.UPLOAD_CONTENTS_AND_METADATA,
                None,
            )

        file_contents_check = self._gateway.check_file_contents_exist(
            file_instance=file_instance
        )
        asset_id = file_contents_check.asset_id

        if file_contents_check.file_exists_in_tree:
            return FileUploadMode.SKIP, asset_id
        if file_contents_check.file_contents_exist_for_user:
            return FileUploadMode.UPLOAD_METADATA_ONLY, asset_id
        return FileUploadMode.UPLOAD_CONTENTS_AND_METADATA, asset_id

    def __str__(self) -> str:
        return f"Client(host={self.host})"


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
