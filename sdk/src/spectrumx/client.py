"""Client for the SpectrumX Data System."""

from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Any

from loguru import logger as log
from pydantic import UUID4

from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.ops.pagination import Paginator

from . import __version__
from .config import SDSConfig
from .gateway import GatewayClient
from .models import File
from .ops import files
from .utils import clean_local_path
from .utils import get_prog_bar
from .utils import log_user
from .utils import log_user_error
from .utils import log_user_warning

if TYPE_CHECKING:
    from tqdm import tqdm


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
                "files are fabricated and not written to disk."
            )
            files_to_download = files.generate_random_files(num_files=10)
            log_user(f"Dry run: discovered {len(files_to_download)} files (samples)")
        else:
            files_to_download = self.list_files(sds_path=from_sds_path)
            if verbose:
                log_user(f"Discovered {len(files_to_download)} files")

        prog_bar: tqdm[File] = get_prog_bar(
            files_to_download, desc="Downloading", disable=not verbose
        )

        results: list[Result[File]] = []
        for file_info in prog_bar:
            prog_bar.set_description(f"{prefix} '{file_info.name}'")
            sds_dir = file_info.directory

            local_file_path = Path(f"{to_local_path}/{sds_dir}") / file_info.name
            local_file_path = clean_local_path(local_file_path)
            # this path will be validated later

            # skip download of local files (without UUID)
            if file_info.uuid is None:
                msg = f"Skipping local file: {file_info.name}"
                log_user_warning(msg)
                results.append(
                    Result(
                        exception=SDSError(msg),
                        error_info={
                            "file": file_info,
                        },
                    )
                )
                continue

            # register failure if the resolved path is not relative to the target
            local_file_path = local_file_path.resolve()
            to_local_path = to_local_path.resolve()
            log.debug(f"Resolved path: {local_file_path}")
            log.debug(f"Target path: {to_local_path}")
            if not local_file_path.is_relative_to(to_local_path):
                msg = (
                    f"Resolved path {local_file_path} is not relative to "
                    f"{to_local_path}: skipping download."
                )
                log_user_warning(msg)
                results.append(
                    Result(
                        exception=SDSError(msg),
                        error_info={
                            "file": file_info,
                        },
                    )
                )
                continue

            # avoid unintended overwrites (success)
            if local_file_path.exists() and not overwrite:
                log_user(f"Skipping existing file: '{local_file_path}'")
                results.append(Result(value=file_info))
                continue

            # download the file and register result
            try:
                log.debug(f"Dw: {local_file_path}")
                downloaded_file = self.download_file(
                    file_uuid=file_info.uuid,
                    to_local_path=local_file_path,
                    skip_contents=skip_contents,
                )
                results.append(Result(value=downloaded_file))
            except SDSError as err:
                log_user_error(f"Download failed: {err}")
                results.append(
                    Result(
                        exception=err,
                        error_info={
                            "file": file_info,
                        },
                    )
                )

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

        > Note this function always overwrites the local file, if it exists.

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


__all__ = ["Client"]
