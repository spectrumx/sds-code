# SpectrumX SDK Changelog

## `0.1.7` - 2025-03-04

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
