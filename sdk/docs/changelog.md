# SpectrumX SDK Changelog

## `0.1.9` - Future

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
