# SpectrumX Data System | SDK

![PyPI - Version](https://img.shields.io/pypi/v/spectrumx)
![PyPI - Python Version](https://img.shields.io/pypi/pyversions/spectrumx)
![Pepy Total Downloads](https://img.shields.io/pepy/dt/spectrumx)
[![SDK Code Quality Checks](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml/badge.svg)](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml)

+ [SpectrumX Data System | SDK](#spectrumx-data-system--sdk)
    + [SDK Usage Guide](#sdk-usage-guide)
    + [System dependencies](#system-dependencies)
    + [SDK Development](#sdk-development)
        + [Local Testing](#local-testing)
        + [Integration Testing](#integration-testing)
        + [Code Quality](#code-quality)
        + [CI/CD](#cicd)
        + [Maintenance](#maintenance)
        + [More testing options](#more-testing-options)

The SDK is the primary form that clients interact with SDS: either directly by installing the Python package from PyPI, or indirectly by using the SDS Web UI or the Visualization Component.

## SDK Usage Guide

This is the development README. See [users' readme](./docs/README.md) for a guide on how to install and use the SDK.

## System dependencies

+ [`uv`](https://docs.astral.sh/uv/getting-started/installation/) - Python environment manager
+ `make` - saves time by automating common tasks
+ GNU `coreutils`, GNU `tar`.
+ Optional:
    + `gh` - GitHub CLI for running GitHub Actions.
    + `gh-act` - `gh` extension for running GitHub Actions locally (incl. pyright action).

Everything else is installed by `uv` in the virtual environment whenever a `uv sync` or `uv run` command is executed.

## SDK Development

GitHub Actions automate code quality checks, testing, and package publishing. See the [makefile](./makefile) and the [GitHub Actions workflows](../.github/workflows/) for specific details.

### Local Testing

```bash
make
# equivalent to `make install test`

make install
# installs project dependencies and pre-commit hooks

make test
# runs pytest with the most recent python version and higher bounds of dependencies

make test-verbose
# like make test, but with extra verbosity and log capture

make test-all
# `make test` + test supported python versions @ lower bound of deps. for compatibility
# expect deprecation warnings for lower bound tests.

make serve-coverage
# serves the coverage report on localhost:8000 - run one of the test targets first
```

### Integration Testing

Integration tests need more setup. You need to deploy the Gateway and Network components, create a test user, and set up the integration test environment:

1. Follow the Network setup instructions in the [Network README](../network/README.md);
    1. Adjust TLS according to your setup;
    2. Modify your local DNS resolution if you'd like to simulate requests to a custom domain;
2. Follow the Gateway instructions in the [Gateway README](../gateway/README.md); In summary:
    1. Deploy the Docker Compose stack;
    2. Create a MinIO user and bucket with same credentials as in `minio.env`;
3. Create a test user and API key:
    1. Create a Gateway superuser and a regular user (they may be the same);
    2. Enable their `is_approved` flag in the [admin panel](http://localhost:8000/admin);
    3. With the flag enabled, login as that user and create an API key for them;
    4. Copy / save the key.
4. Integration test setup:
    1. Create `tests/integration/integration.env` from its example counterpart
    2. Set the api key to the one created.
    3. Run the `make test-integration` target.

Then you can run the integration tests:

```bash
make test-integration
# runs integration tests with pytest

make test-integration-verbose
# like make test-integration, but with extra verbosity and log capture
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
# runs all GitHub Actions locally with gh-act
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
# updates dependencies with uv and updates the pre-commit hooks
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
