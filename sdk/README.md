# SpectrumX Data System | SDK

![PyPI - Version](https://img.shields.io/pypi/v/spectrumx)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/spectrumx)
![Pepy Total Downloads](https://img.shields.io/pepy/dt/spectrumx)
[![SDK Code Quality Checks](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml/badge.svg)](<https://github.com/spectrumx/sds-code/actions/workflows/>
sdk-checks.yaml)

+ [SpectrumX Data System | SDK](#spectrumx-data-system--sdk)
    + [Usage Guide](#usage-guide)
    + [SDK Development](#sdk-development)
        + [Make targets](#make-targets)
        + [More Testing](#more-testing)

The SDK is the primary form that clients interact with SDS: either directly by installing the Python package from PyPI, or indirectly by using the SDS Web UI or the Visualization Component.

## Usage Guide

This is the development README. See [users' readme](./docs/README.md) for a guide on how to install and use the SDK.

## SDK Development

### Make targets

```bash
make
# equivalent to make install test

make install
# runs uv sync

make test-all
# runs tox for all supported python versions

make test
# runs pytest on most recent python version

make test-verbose
# runs pylint on most recent python version with extra verbosity and log capture

make serve-coverage
# serves coverage report on localhost:8000

make gact
# runs GitHub Actions locally with gh-act
#
# >>> WARNING: if the secrets file has a valid API key,
#   this target will actually publish the package to PyPI.
#
# Install with:     gh extension install nektos/gh-act
# or see            https://github.com/nektos/act

make clean
# removes all venv, tox, cache, and generated files

make update
# updates uv and pre-commit hooks

make build
# builds the package to dist/ and previews it

make publish
# publishes the package to PyPI
#
# >>> WARNING: if the secrets file has a valid API key,
#   this target will actually publish the package to PyPI.
```

### More Testing

```bash
uv sync --dev

# simple tests execution (similar to `make test`)
uv run pytest -v

# running a specific test
uv run pytest -v tests/test_usage.py::test_authentication_200_succeeds

# running similar tests (substring match)
uv run pytest -v -k test_authentication

# verbose with colored log messages (similar to `make test-verbose`)
uv run pytest -vvv --show-capture=stdout -o log_cli=true --log-cli-level=DEBUG --capture=no
```
