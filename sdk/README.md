# SpectrumX Data System | SDK

![PyPI - Version](https://img.shields.io/pypi/v/spectrumx)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/spectrumx)
![Pepy Total Downloads](https://img.shields.io/pepy/dt/spectrumx)
[![SDK Code Quality Checks](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml/badge.svg)](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml)

+ [SpectrumX Data System | SDK](#spectrumx-data-system--sdk)
    + [Usage Guide](#usage-guide)
    + [SDK Development](#sdk-development)
        + [Testing](#testing)
        + [Code Quality](#code-quality)
        + [CI/CD](#cicd)
        + [Maintenance](#maintenance)
        + [More testing options](#more-testing-options)

The SDK is the primary form that clients interact with SDS: either directly by installing the Python package from PyPI, or indirectly by using the SDS Web UI or the Visualization Component.

## Usage Guide

This is the development README. See [users' readme](./docs/README.md) for a guide on how to install and use the SDK.

## SDK Development

### Testing

```bash
make
# equivalent to make install test

make install
# runs uv sync

make test
# runs pytest on most recent python version

make test-verbose
# runs pytest on most recent python version with extra verbosity and log capture

make test-all
# runs tests for all supported python versions using the highest and lowest versions of dependencies

make serve-coverage
# serves coverage report on localhost:8000
```

### Code Quality

```bash
make pyright
# runs pyright for static type checking

make pre-commit
# runs pre-commit hooks on all files
```

### CI/CD

```bash
make gact
# runs GitHub Actions locally with gh-act
#
# >>> WARNING: if the secrets file has a valid API key,
#   this target will actually publish the package to PyPI.
#
# Install with:     gh extension install nektos/gh-act
# or see            https://github.com/nektos/act

make build
# builds the package to dist/ and previews it

make publish
# publishes the package to PyPI
#
# >>> WARNING: if the secrets file has a valid API key,
#   this target will actually publish the package to PyPI.
```

### Maintenance

```bash
make clean
# removes all venv, tox, cache, and generated files

make update
# updates dependencies with uv and the pre-commit hooks
```

### More testing options

```bash
# simple tests execution (similar to `make test`)
uv run pytest -v

# running similar tests (substring match)
uv run pytest -v -k test_authentication

# running a specific test
uv run pytest -v tests/test_usage.py::test_authentication_200_succeeds

# verbose with colored log messages (similar to `make test-verbose`)
uv run pytest -vvv --show-capture=stdout -o log_cli=true --log-cli-level=DEBUG --capture=no
```
