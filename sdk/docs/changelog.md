# SpectrumX SDK Changelog

## `0.1.5` - Future

+ Breaking changes:
    + `spectrumx.models.File` moved to `spectrumx.models.files.File`.
+ New features:
    + TODO: SDS Capture creation, reading, and listing.
    + TODO: Introducing client identification and "outdated client" version warning when authenticating (gateway + SDS).
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
