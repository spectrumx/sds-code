"""Client for the SpectrumX Data System."""

from collections.abc import Mapping
from pathlib import Path
from pathlib import PurePosixPath
from typing import TYPE_CHECKING
from typing import Any
from uuid import UUID

from loguru import logger as log
from pydantic import UUID4

from spectrumx.api.captures import CaptureAPI
from spectrumx.errors import CaptureError
from spectrumx.errors import Result
from spectrumx.errors import SDSError
from spectrumx.errors import process_upload_results
from spectrumx.models.captures import Capture
from spectrumx.models.captures import CaptureType
from spectrumx.ops.pagination import Paginator

from . import __version__
from .config import SDSConfig
from .gateway import GatewayClient
from .models.files import File
from .ops import files
from .utils import clean_local_path
from .utils import get_prog_bar
from .utils import log_user
from .utils import log_user_error
from .utils import log_user_warning

if TYPE_CHECKING:
    from tqdm import tqdm


class Client:
    """Instantiates an SDS client."""

    host: str
    is_authenticated: bool
    captures: CaptureAPI

    _verbose: bool = False
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
        self._verbose = verbose
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

        # create internal API instances
        self.captures = CaptureAPI(
            gateway=self._gateway,
            dry_run=self.dry_run,
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
    def verbose(self) -> bool:
        """When True, shows verbose output."""
        return self._verbose

    @verbose.setter
    def verbose(self, value: bool) -> None:
        """Sets the verbose mode for the client and internal API instances."""
        self._verbose = bool(value)
        self._gateway.verbose = self._verbose
        self.captures.verbose = self._verbose
        self.captures.verbose = self._verbose
        # add future API instances here

    @property
    def dry_run(self) -> bool:
        """When in dry run mode, no SDS requests are made and files are not written."""
        return self._config.dry_run

    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        """Sets the dry run mode for the client and internal API instances."""

        self._config.dry_run = bool(value)
        self.captures.dry_run = self._config.dry_run
        # add future API instances here

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
            log.warning(f"Dry run DISABLED: authenticating against '{self.host}'")
            self._gateway.authenticate()
        log.info("Authenticated successfully")
        self.is_authenticated = True

    # ======= FILE METHODS

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

    def delete_file(self, file_uuid: UUID4 | str) -> bool:
        """Deletes a file from SDS by its UUID.

        Args:
            file_uuid: The UUID of the file to delete.
        Returns:
            True if the file was deleted successfully,
            or if in dry run mode (simulating success).
        Raises:
            SDSError: If the file couldn't be deleted.
        """
        return self._sds_files.delete_file(client=self, file_uuid=file_uuid)

    def download(
        self,
        *,
        from_sds_path: PurePosixPath | Path | str,
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
        from_sds_path = PurePosixPath(from_sds_path)
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
        self, sds_path: PurePosixPath | Path | str, *, verbose: bool = False
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
        sds_path: PurePosixPath | Path | str = "/",
        verbose: bool = True,
        warn_skipped: bool = True,
    ) -> list[Result[File]]:
        """Uploads a file or directory to SDS.

        Args:
            local_path:     The local path of the file or directory to upload.
            sds_path:       The virtual directory on SDS to upload the file to, \
                                where '/' is the user root.
            verbose:        Show a progress bar.
            warn_skipped:   Display warnings for skipped files.
        """
        local_path = Path(local_path) if isinstance(local_path, str) else local_path
        valid_files = files.get_valid_files(local_path, warn_skipped=warn_skipped)
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
        sds_path: PurePosixPath | Path | str = "/",
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

    def upload_capture(
        self,
        *,
        local_path: Path | str,
        sds_path: PurePosixPath | Path | str = "/",
        capture_type: CaptureType,
        index_name: str = "",
        channel: str | None = None,
        scan_group: str | None = None,
        verbose: bool = True,
        warn_skipped: bool = False,
        raise_on_error: bool = True,
    ) -> Capture | None:
        """Uploads a local directory and creates a capture using those files.

        This method effectively combines `Client.upload()` and
            `Client.captures.create_capture()` into one call. For a more fine-grained
            control, call each method separately.

        Args:
            local_path:     The local path of the directory to upload.
            sds_path:       The virtual directory on SDS to upload the file to.
            capture_type:   One of `spectrumx.models.captures.CaptureType`.
            index_name:     The SDS index name. Leave empty to automatically select.
            channel:        (For Digital-RF) the DRF channel name to index.
            scan_group:     (For RadioHound) UUIDv4 that groups RH files.
            verbose:        Show progress bar and failure messages, if any.
            raise_on_error: When True, raises an exception if any file upload fails.
                            If False, the method will return None and log the errors.
        Returns:
            The created capture object when all operations succeed.
        Raises:
            When `raise_on_error` is True.
            FileError:      If any file upload fails.
            CaptureError:   If the capture creation fails.
        """

        upload_results = self.upload(
            local_path=local_path,
            sds_path=sds_path,
            verbose=verbose,
            warn_skipped=warn_skipped,
        )

        if not process_upload_results(
            upload_results,
            raise_on_error=raise_on_error,
            verbose=verbose,
        ):
            return None

        try:
            capture = self.captures.create(
                top_level_dir=PurePosixPath(sds_path),
                capture_type=capture_type,
                index_name=index_name,
                channel=channel,
                scan_group=scan_group,
            )
        except SDSError:
            if raise_on_error:
                raise
            if verbose:
                log_user_error("Failed to create capture.")
            return None
        else:
            return capture

    def _handle_existing_capture_error(
        self,
        err: SDSError,
    ) -> tuple[bool, Capture | None]:
        """
        Handle the case where a capture already exists.
        Returns True if handled, False otherwise.
        """
        if not isinstance(err, CaptureError):
            return False, None

        existing_uuid_str = err.extract_existing_capture_uuid()
        if not existing_uuid_str:
            return False, None

        try:
            existing_uuid = UUID(existing_uuid_str)
            existing_capture = self.captures.read(capture_uuid=existing_uuid)
        except (SDSError, ValueError):
            return False, None
        else:
            return True, existing_capture

    def upload_multichannel_drf_capture(
        self,
        *,
        local_path: Path | str,
        sds_path: PurePosixPath | Path | str = "/",
        channels: list[str],
        verbose: bool = True,
        warn_skipped: bool = False,
        raise_on_error: bool = True,
    ) -> list[Capture] | None:
        """Uploads a capture with multiple channels by running `upload`
        once for the whole directory. Then, it creates a capture for each channel.

        *Note: This method is only for DigitalRF captures.*

        Args:
            local_path: The local path of the directory to upload.
            sds_path: The virtual directory on SDS to upload the file to.
            channels: The list of channels to create captures for.
            verbose: Show progress bar and failure messages, if any.
            warn_skipped: Display warnings for skipped files.
            raise_on_error: When True, raises an exception if any file upload fails.
                            If False, the method will return an empty list
                            or None and log the errors.
        Returns:
            A list of captures created for each channel,
            or an empty list if any capture creation fails or no channels are provided.
        Raises:
            When `raise_on_error` is True.
            FileError: If any file upload fails.
        """
        upload_results = self.upload(
            local_path=local_path,
            sds_path=sds_path,
            verbose=verbose,
            warn_skipped=warn_skipped,
        )

        if not process_upload_results(
            upload_results,
            raise_on_error=raise_on_error,
            verbose=verbose,
        ):
            return None

        captures: list[Capture] = []

        if len(channels) == 0:
            log_user_warning("No channels provided, skipping capture creation")
            return captures

        for channel in channels:
            try:
                capture = self.captures.create(
                    top_level_dir=PurePosixPath(sds_path),
                    capture_type=CaptureType.DigitalRF,
                    channel=channel,
                )
            except SDSError as err:
                if verbose:
                    log_user_error(
                        f"Failed to create multi-channel capture for channel: {channel}"
                    )
                # If capture already exists, try to get it instead of
                # deleting all captures
                capture_found, existing_capture = self._handle_existing_capture_error(
                    err
                )
                if capture_found:
                    assert existing_capture is not None
                    captures.append(existing_capture)
                else:
                    # Cleanup any created captures
                    for created_capture in captures:
                        if created_capture.uuid is not None:
                            self.captures.delete(capture_uuid=created_capture.uuid)

                    return []
            else:
                captures.append(capture)
        return captures


__all__ = ["Client"]
