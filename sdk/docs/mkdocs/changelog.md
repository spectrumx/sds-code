# SpectrumX SDK Changelog

## `0.2.0` - 2026-07-06

+ Features:
    + [**Byte-level progress bars for file
      downloads**](https://github.com/spectrumx/sds-code/pull/306): file downloads now
      show a byte-level progress bar with throttled `tqdm` callbacks (~100 KB refresh
      rate), providing smooth visual feedback during multi-file downloads — matching the
      upload progress bar experience introduced in v0.1.15. When total bytes are unknown
      (e.g. paginated results), a file-level fallback progress bar is used instead.
    + [**Configurable periodic progress
      logging**](https://github.com/spectrumx/sds-code/pull/306): new
      `progress_log_period_secs` config option (default: 30 seconds) controls how often
      structured progress log entries are emitted during long-running uploads and
      downloads. Set via environment variable or `.env` file.
    + [**Custom structured log path**](https://github.com/spectrumx/sds-code/pull/306):
      new `log_file` config option allows setting a custom path for the structured JSONL
      log file via environment variable, `.env` file, or `Client(log_file=...)`
      parameter.

+ Observability:
    + [**Structured JSONL logging
      system**](https://github.com/spectrumx/sds-code/pull/306): new
      `enable_structured_logging()` function configures the SDK to write
      machine-parseable JSON lines to `~/.local/state/spectrumx/logs/YYYY-MM-DD.jsonl`.
      Each log line includes timestamp, process ID, severity, category, and message. Use
      `jq` to filter and analyze:

      ```bash
      # Show only download operations
      jq 'select(.cat == "download")' ~/.local/state/spectrumx/logs/*.jsonl

      # Show warnings and errors
      jq 'select(.lvl == "WARNING" or .lvl == "ERROR")' ~/.local/state/spectrumx/logs/*.jsonl
      ```

        + Boot message with SDK version, OS platform, and Python version on every
          session.
        + Log categories: `config`, `auth`, `network`, `filesystem`, `download`,
          `upload`, `log`.
        + Scoped context via `LogContext` context manager for per-operation fields (e.g.
          upload ID, directory).
        + Persistent context via `set_persistent_log_context()` for cross-operation
          fields (e.g. API key prefix).
        + Error entries include exception type and message in `exc_info` field.
        + Re-configurable at runtime — calling `enable_structured_logging()` with a new
          path switches to the new file and emits a fresh boot message.
    + **Upload workflow now emits structured log entries**:
        + Periodic progress every `progress_log_period_secs` with completed/total files,
          bytes uploaded/total, failures, in-progress, and skipped counts.
        + Completion summary with elapsed time, average speed, and status
          (clean/interrupted).
        + Per-file operation log context via `log_context(upload_id=...,
          upload_dir=...)`.
    + **Download workflow now emits structured log entries**:
        + Per-file completion with file name and size.
        + Periodic progress every `progress_log_period_secs` with completed/total files,
          bytes downloaded/total, and failure count.
        + Completion summary with elapsed time, average speed, and status
          (clean/interrupted).
    + **Configuration events tagged with `LogCategory.CONFIG`** — config loading, env
      file discovery, and attribute setting now emit structured log entries for easier
      debugging.

+ Housekeeping:
    + [**Developer demo script**](https://github.com/spectrumx/sds-code/pull/306): added
      `scripts/demo_progress_bars.py` that simulates upload/download transfers at
      configurable rates to let developers preview progress bar visuals without a live
      gateway.
    + [**Improved test coverage**](https://github.com/spectrumx/sds-code/pull/306):
        + New `test_structured_logging.py` module (9 tests): JSONL file paths, boot
          message emission, core fields on every log line, contextual field binding,
          category filtering, scoped context lifecycle, persistent context, path
          re-configuration, and state reset.
        + New download byte progress tests in `test_client.py` covering skipped content
          credit and partial stream accounting.
        + New upload progress tests in `test_uploads_workflow.py` covering unstreamed
          byte credit, metadata-only uploads, and concurrent progress bar byte counting.
        + New `credit_unstreamed_file_bytes` tests in `test_utils.py`.
    + Version bump to `0.2.0`.

## `0.1.20` - 2026-06-02

+ Fixes:
    + **Fixed crash when `owner` and related fields are missing from API responses**:
      the `Capture.owner` field (and `User.name`/`User.email` for cascading partial
      data) are now optional with `None` defaults. Previously, the SDK would raise a
      Pydantic `ValidationError` when the server omitted these fields from capture
      payloads during file and capture listing, causing the entire operation to fail.

## `0.1.19` - 2026-05-15

+ Features:
    + [**Added `start_time` and `end_time` parameters to `list_files` and `download`**](https://github.com/spectrumx/sds-code/pull/278): this gives users the ability to filter file directory downloads associated with DigitalRF captures based on a time span within the capture bounds (similar to time filtering in the web UI on SDS)
    + [**Added `capture_uuids`, `top_level_dirs`, and `artifacts_only` parameters to `download_dataset`**](https://github.com/spectrumx/sds-code/pull/278): this allows users to input specific capture UUIDs or file directories associated with the dataset to download. `artifacts_only` allows user to filter for directly connected files on a dataset specifically. In this case, `capture_uuids` entry is ignored, but users may define `top_level_dir` file directories to filter artifacts for download on a large dataset. Users may run `list_dataset_captures` to see the UUID and `top_level_dir` of the captures on the dataset they wish to download.
    + [**Added `list_dataset_captures` method**](https://github.com/spectrumx/sds-code/pull/278): this allows users to list all captures associated with a dataset.
    + [**Added `list_dataset_artifact_files` method**](https://github.com/spectrumx/sds-code/pull/278): this allows users to list all artifact files associated with a dataset.

+ Observability:
    + [**Added `captures` and `files` attributes to `Dataset` model**](https://github.com/spectrumx/sds-code/pull/278): This allows visibility from the dataset side into attached captures and files.
    + [**Added `capture_start_iso_utc`, `capture_end_iso_utc`, `capture_start_display`, and `capture_end_display` fields to the `Capture` model**](https://github.com/spectrumx/sds-code/pull/278): Users can now inspect the indexed capture time bounds from OpenSearch on capture metadata, both in UTC and in a display-formatted time zone.
    + [**Added `gateway` property to `Client`**](https://github.com/spectrumx/sds-code/pull/278): Advanced users and test code can now access the underlying `GatewayClient` directly via `sds.gateway`.

+ Housekeeping:
    + [**Paginator now surfaces API warnings**](https://github.com/spectrumx/sds-code/pull/278): When the server returns warning messages in paginated responses, they are now logged automatically via the SDK's logger.

## `0.1.18` - 2026-04-30

+ Features:
    + [**Added `delete` and `revoke_share_permissions` methods for
      datasets**](https://github.com/spectrumx/sds-code/pull/275): this allows users to
      (soft) delete datasets in the SDS through the SDK and revoke ALL share permissions
      from datasets if needed before deletion or in general.
    + [**Added `revoke_share_permissions` and `detach_from_datasets` methods to
      captures**](https://github.com/spectrumx/sds-code/pull/275): this gives users the
      ability to revoke share permissions or detach captures from connected datasets
      when they need to delete a capture.
    + [**Added `detach_from_datasets` methods to
      files**](https://github.com/spectrumx/sds-code/pull/275): this gives users the
      ability to detach files from connected datasets when they need to delete them.
      Note: Files CANNOT be detached from captures. Delete a the parent capture FIRST to
      delete the file.

+ Observability:
    + [**Added fields displaying ownership, share permission, and asset
      connection information to SDK
      models**](https://github.com/spectrumx/sds-code/pull/275): this allows users to
      see more relevant information when retrieving or listing assets like whether they
      are shared, who they are shared with, who owns them, and what other assets the
      target is attached to (like files to captures and datasets).
        + New file attributes: `owner`, `captures`, `datasets`
        + New capture attributes: `owner`, `is_shared`, `is_shared_with_me`,
          `share_permissions`
        + New dataset attributes: `owner`, `is_shared`, `share_permissions`, `datasets`
    + [**Added new models for User and
      UserSharePermission**](https://github.com/spectrumx/sds-code/pull/275): This
      allows for visibility into the users and share permissions connected to assets.

+ Fixes:
    + [**Fixed upload failure when using relative local
      paths**](https://github.com/spectrumx/sds-code/pull/279): the file discovery step
      in uploads broke when a relative path was given as `local_path` (e.g.
      `sds.upload(local_path="my_dir", ...)`). The root cause was passing the resolved
      (absolute) root path but feeding candidates from an unresolved (relative) `rglob`
      iterator, causing `Path.relative_to()` to fail with a `ValueError`. This was a
      regression introduced in v0.1.15 when switching to `anyio.Path` for async path
      operations.

## `0.1.17` - 2025-12-20

+ Fixes:
    + [**Improved file downloads**](https://github.com/spectrumx/sds-code/pull/236):
      more reliability for file downloads when they need to be resumed.
        + File downloads now use a temporary file during download to avoid partial files
          being left behind if the download is interrupted.
        + When overwrite is `False` and a local file would be overwritten, we skip
          re-downloading it.
        + When overwrite is `True` and the checksums don't match with server, we
          re-download and replace the local file to match the server's.
        + If local file is identical to server's, we now skip the download entirely,
          even when overwrite is `True`.

## `0.1.16` - 2025-12-16

+ Fixes:
    + [**Added `persist_state` to
      `upload_multichannel_drf_capture`**](https://github.com/spectrumx/sds-code/pull/230):
      users can now control whether to persist the upload state of files during
      multi-channel DRF captures.
+ Reliability:
    + [**Relaxed validation in capture
      listing**](https://github.com/spectrumx/sds-code/pull/230): capture listing is now
      more tolerant of cases where a given capture fails validation, now listing the
      ones that can be loaded correctly instead of failing the whole operations.
      Container fields like `files` now also default to empty ones if missing, instead
      of failing validation.

## `0.1.15` - 2025-12-02

+ Features:
    + [**Added support for Python
      3.14**](https://github.com/spectrumx/sds-code/pull/210): the SDK is now compatible
      with Python 3.14. We're thus dropping support for version 3.10 in this and future
      releases.
    + [**Improved UX for file
      uploads**](https://github.com/spectrumx/sds-code/pull/218): the new file upload
      process:
        + Backwards compatible with previous method.
        + Discovery step lists all files before starting upload.
        + Concurrent uploads with asyncio: up to 5 streams by default.
        + Progress tracking the number of files and bytes, in human-friendly units.
        + Tracking completed :white_check_mark:, failed :x: , in progress
          :hourglass_flowing_sand:️ and skipped:rabbit2: files. On Windows, we use ASCII
          characters for better compatibility.
    + [**New file upload persistence**](https://github.com/spectrumx/sds-code/pull/218):
      we now keep a local copy of the upload state of files.
        + This makes resuming interrupted uploads faster. The persistence mode can be
          bypassed with `persist_state=False` in upload methods in case users want to
          force the file checks (previous behavior).
+ Reliability:
    + Increased the battery of tests for file uploads and progress tracking.
    + Several new tests covering features of upload state persistence.

## `0.1.14` - 2025-10-07

+ Documentation:
    + **Added and SDK walkthrough notebook** to the users' guide: [SpectrumX SDK
      walkthrough](https://github.com/crcresearch/spx-events/blob/main/demos/data_system/walkthrough.ipynb).
+ Fixes:
    + [**Reviewed logic to ignore
      files**](https://github.com/spectrumx/sds-code/pull/191): now files like
      `.DS_Store`, `*.tmp`, and other patterns in
      [.sds-ignore](https://github.com/spectrumx/sds-code/blob/a7aabce571108d07a80efcc88feb15fe66a2a35a/sdk/src/spectrumx/ops/.sds-ignore)
      are correctly skipped for uploads.

## `0.1.13` - 2025-08-26

+ Features:
    + [**Added `download_dataset` method to
      client**](https://github.com/spectrumx/sds-code/pull/165): Users can now download
      datasets through the SDK by passing in a dataset UUID e.g.
      `sds_client.download_dataset(uuid=<dataset_uuid>, to_local_path=...)`.
    + [**Added a `files_to_download` argument to the `download()`
      method**](https://github.com/spectrumx/sds-code/pull/165): Can now supply a
      pre-filtered list of files to download rather than downloading all files in a
      path.

## `0.1.12` - 2025-08-12

+ Features:
    + [**Added `name` parameter to `upload_capture`
      method**](https://github.com/spectrumx/sds-code/pull/143): `upload_capture()` now
      accepts an optional `name` parameter to set custom capture names.

## `0.1.11` - 2025-07-03

+ Features:
    + [**Added `upload_multichannel_drf_capture` SDK method to
      `Client`**](https://github.com/spectrumx/sds-code/pull/137): Multi-channel
      captures can now be uploaded to the SDS.

## `0.1.10` - 2025-06-05

+ Features:
    + [**Added `created_at` to
      captures:**](https://github.com/spectrumx/sds-code/pull/106): captures now feature
      a `created_at` datetime attribute when this information is available.
    + [**Allowing upload of sigmf-data
      files**](https://github.com/spectrumx/sds-code/pull/110): removed restriction of
      octet-stream files in uploads.

## `0.1.9` - 2025-05-08

+ Features:
    + [**Capture deletions:**](https://github.com/spectrumx/sds-code/pull/84) captures
      may now be deleted using the SDK with `sds_client.captures.delete()`.
    + [**Advanced searches:**](https://github.com/spectrumx/sds-code/pull/90)
      introducing preliminary support for *advanced capture searches* using OpenSearch
      queries. See the [OpenSearch Query
      Tips](https://github.com/spectrumx/sds-code/tree/master/gateway#opensearch-query-tips)
      for details about the syntax. The SDK endpoint is
      `sds_client.captures.advanced_search()`: the method's docstring has information on
      arguments and links to documentation.
+ Usage improvements:
    + [**Allowing positional args:**](https://github.com/spectrumx/sds-code/pull/84) SDK
      methods that receive a single UUID as an argument now allow it to be passed as a
      positional argument e.g. `sds_client.get_file(<uuid>)` is equivalent to
      `sds_client.get_file(uuid=<uuid>)`.
    + [**Capture uploads:**](https://github.com/spectrumx/sds-code/pull/93) new
      high-level method that combines the upload of a directory of files with a capture
      creation: `sds_client.upload_capture()`.
    + [**Usage guide
      updates:**](https://github.com/spectrumx/sds-code/blob/master/sdk/docs/README.md)
      the SDK usage guide now includes information on how to check the results returned
      by a directory upload.
    + [**Logging control:**](https://github.com/spectrumx/sds-code/pull/95): client's
      verbose flag propagates to submodules and sub-APIs.
+ Bugfixes and reliability improvements:
    + [**Bugfix:**](https://github.com/spectrumx/sds-code/pull/95) `File.local_path`
      attribute of some downloaded files was not correctly set.
    + [**Path usage tests:**](https://github.com/spectrumx/sds-code/pull/95): new tests
      to cover regressions of different ways to use paths from SDK methods.
    + [**Capture read test:**](https://github.com/spectrumx/sds-code/pull/95) tests for
      `client.capture.read()` now check the number of files associated to the capture is
      correct.

## `0.1.8` - 2025-03-24

+ Features and improvements:
    + [#72](https://github.com/spectrumx/sds-code/pull/72) Added Windows compatibility.
    + [#79](https://github.com/spectrumx/sds-code/pull/79) SDS files may now be deleted
      using the SDK.
    + [#78](https://github.com/spectrumx/sds-code/pull/78) The `capture_type` argument
      of `sds_client.captures.listing()` is now optional.
    + [#78](https://github.com/spectrumx/sds-code/pull/78) The method
      `sds_client.captures.read()` is now available for reading a single capture,
      complementing the existing `sds_client.captures.listing()` method.
    + [#78](https://github.com/spectrumx/sds-code/pull/78) When retrieving a single
      capture with `capture = read(<uuid>)`, the list of files associated to it is
      available in `capture.files`.
        + Note these are `CaptureFile` instances, which hold a subset of the information
          in an SDS' `File` instance. To get all metadata on a file, use
          `sds_client.get_file(<uuid>)`.
+ Fixes:
    + [#77](https://github.com/spectrumx/sds-code/pull/77) Fixed incorrect file name
      being set when the file contents are already in SDS.
    + [#77](https://github.com/spectrumx/sds-code/pull/77) `local_path` is now set for
      uploaded files across all three upload modes.
    + [#71](https://github.com/spectrumx/sds-code/pull/71) File permissions are now
      included in file uploads; redesigned handling of permission flags.
+ Housekeeping:
    + [#76](https://github.com/spectrumx/sds-code/pull/76) Fixed documentation typos;
      Updated and expanded note on concurrent access in the usage guide.

## `0.1.7` - 2025-03-07

+ Features:
    + `spectrumx.api.captures.create()` now accepts a `scan_group` for RadioHound
      captures.
    + `index_name` from `spectrumx.api.captures.create()` is dropped: the index is
      automatically chosen from the capture type.

## `0.1.6` - 2025-02-24

+ New features:
    + Support for Python 3.10 and 3.11.

## `0.1.5` - 2025-02-10

+ Breaking changes:
    + `spectrumx.models.File` moved to `spectrumx.models.files.File`.
+ New features:
    + SDS Capture creation and listing.
+ Housekeeping:
    + Refactored client by branching its method implementations and client configuration
      to separate modules.

## `0.1.4` - 2025-01-17

+ New features:
    + File listing with lazy-loaded paginated results.
    + Introduced new file upload modes to avoid re-uploading files already in SDS.
+ Housekeeping:
    + Usage documentation updated.
    + See `tests/e2e_examples/check_build_acceptance.py` for more SDK usage examples.
    + Refactoring of internal modules.
    + Improved test coverage.
