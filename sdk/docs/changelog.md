# SpectrumX SDK Changelog

## `0.1.12` - 2025-07-xx

## `0.1.11` - 2025-07-03

+ Features:
    + [**Added `upload_multichannel_drf_capture` SDK method to `Client`**](https://github.com/spectrumx/sds-code/pull/137): Multi-channel captures can now be uploaded to the SDS.

## `0.1.10` - 2025-06-05

+ Features:
    + [**Added `created_at` to captures:**](https://github.com/spectrumx/sds-code/pull/106): captures now feature a `created_at` datetime attribute when this information is available.
    + [**Allowing upload of sigmf-data files**](https://github.com/spectrumx/sds-code/pull/110): removed restriction of octet-stream files in uploads.

## `0.1.9` - 2025-05-08

+ Features:
    + [**Capture deletions:**](https://github.com/spectrumx/sds-code/pull/84) captures may now be deleted using the SDK with `sds_client.captures.delete()`.
    + [**Advanced searches:**](https://github.com/spectrumx/sds-code/pull/90) introducing preliminary support for *advanced capture searches* using OpenSearch queries. See the [OpenSearch Query Tips](https://github.com/spectrumx/sds-code/tree/master/gateway#opensearch-query-tips) for details about the syntax. The SDK endpoint is `sds_client.captures.advanced_search()`: the method's docstring has information on arguments and links to documentation.
+ Usage improvements:
    + [**Allowing positional args:**](https://github.com/spectrumx/sds-code/pull/84) SDK methods that receive a single UUID as an argument now allow it to be passed as a positional argument e.g. `sds_client.get_file(<uuid>)` is equivalent to `sds_client.get_file(uuid=<uuid>)`.
    + [**Capture uploads:**](https://github.com/spectrumx/sds-code/pull/93) new high-level method that combines the upload of a directory of files with a capture creation: `sds_client.upload_capture()`.
    + [**Usage guide updates:**](https://github.com/spectrumx/sds-code/blob/master/sdk/docs/README.md) the SDK usage guide now includes information on how to check the results returned by a directory upload.
    + [**Logging control:**](https://github.com/spectrumx/sds-code/pull/95): client's verbose flag propagates to submodules and sub-APIs.
+ Bugfixes and reliability improvements:
    + [**Bugfix:**](https://github.com/spectrumx/sds-code/pull/95) `File.local_path` attribute of some downloaded files was not correctly set.
    + [**Path usage tests:**](https://github.com/spectrumx/sds-code/pull/95): new tests to cover regressions of different ways to use paths from SDK methods.
    + [**Capture read test:**](https://github.com/spectrumx/sds-code/pull/95) tests for `client.capture.read()` now check the number of files associated to the capture is correct.

## `0.1.8` - 2025-03-24

+ Features and improvements:
    + [#72](https://github.com/spectrumx/sds-code/pull/72) Added Windows compatibility.
    + [#79](https://github.com/spectrumx/sds-code/pull/79) SDS files may now be deleted using the SDK.
    + [#78](https://github.com/spectrumx/sds-code/pull/78) The `capture_type` argument of `sds_client.captures.listing()` is now optional.
    + [#78](https://github.com/spectrumx/sds-code/pull/78) The method `sds_client.captures.read()` is now available for reading a single capture, complementing the existing `sds_client.captures.listing()` method.
    + [#78](https://github.com/spectrumx/sds-code/pull/78) When retrieving a single capture with `capture = read(<uuid>)`, the list of files associated to it is available in `capture.files`.
        + Note these are `CaptureFile` instances, which hold a subset of the information in an SDS' `File` instance. To get all metadata on a file, use `sds_client.get_file(<uuid>)`.
+ Fixes:
    + [#77](https://github.com/spectrumx/sds-code/pull/77) Fixed incorrect file name being set when the file contents are already in SDS.
    + [#77](https://github.com/spectrumx/sds-code/pull/77) `local_path` is now set for uploaded files across all three upload modes.
    + [#71](https://github.com/spectrumx/sds-code/pull/71) File permissions are now included in file uploads; redesigned handling of permission flags.
+ Housekeeping:
    + [#76](https://github.com/spectrumx/sds-code/pull/76) Fixed documentation typos; Updated and expanded note on concurrent access in the usage guide.

## `0.1.7` - 2025-03-07

+ Features:
    + `spectrumx.api.captures.create()` now accepts a `scan_group` for RadioHound captures.
    + `index_name` from `spectrumx.api.captures.create()` is dropped: the index is automatically chosen from the capture type.

## `0.1.6` - 2025-02-24

+ New features:
    + Support for Python 3.10 and 3.11.

## `0.1.5` - 2025-02-10

+ Breaking changes:
    + `spectrumx.models.File` moved to `spectrumx.models.files.File`.
+ New features:
    + SDS Capture creation and listing.
+ Housekeeping:
    + Refactored client by branching its method implementations and client configuration to separate modules.

## `0.1.4` - 2025-01-17

+ New features:
    + File listing with lazy-loaded paginated results.
    + Introduced new file upload modes to avoid re-uploading files already in SDS.
+ Housekeeping:
    + Usage documentation updated.
    + See `tests/e2e_examples/check_build_acceptance.py` for more SDK usage examples.
    + Refactoring of internal modules.
    + Improved test coverage.
