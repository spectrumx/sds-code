# SpectrumX Data System | SDK

[![PyPI -
Version](https://img.shields.io/pypi/v/spectrumx)](https://pypi.org/project/spectrumx/)
[![PyPI - Python
Versions](https://img.shields.io/pypi/pyversions/spectrumx)](https://pypi.org/project/spectrumx/)
[![Pepy Total
Downloads](https://img.shields.io/pepy/dt/spectrumx)](https://pypi.org/project/spectrumx/)
[![SDK Code Quality
Checks](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml/badge.svg)](https://github.com/spectrumx/sds-code/actions/workflows/sdk-checks.yaml)

+ [SpectrumX Data System | SDK](#spectrumx-data-system--sdk)
    + [SDK Usage Guide](#sdk-usage-guide)
    + [System dependencies](#system-dependencies)
    + [SDK Development](#sdk-development)
        + [Just recipes](#just-recipes)
        + [Integration Testing](#integration-testing)
        + [More testing options](#more-testing-options)

The SDK is the primary form that clients interact with SDS: either directly by
installing the Python package from PyPI, or indirectly by using the SDS Web UI or the
Visualization Component.

## SDK Usage Guide

This is the development README. See [users' readme](./docs/README.md) for a guide on how
to install and use the SDK.

## System dependencies

+ [`uv`](https://docs.astral.sh/uv/getting-started/installation/) - Python environment
  manager
+ [`just`](https://github.com/casey/just#installation/) - saves time by automating
  common tasks
+ GNU `coreutils`, GNU `tar`.
+ Optional:
    + `gh` - GitHub CLI for running GitHub Actions.
    + `gh-act` - `gh` extension for running GitHub Actions locally (incl. pyright
      action).

Everything else is installed by `uv` in the virtual environment whenever a `uv sync` or
`uv run` command is executed.

## SDK Development

GitHub Actions automate code quality checks, testing, and package publishing. See the
[justfile](./justfile) and the [GitHub Actions workflows](../.github/workflows/) for
specific details.

### Just recipes

```bash
just --list
```

```bash
Available recipes:
    build                                           # builds the package and runs smoke tests on the built artifact
    check-acceptance                                # checks the built package acceptance tests
    clean                                           # removes temporary and build files
    dev-setup                                       # installs the development environment with pre-commit hooks and synced deps [alias: install]
    gact                                            # runs GitHub Actions locally
    pre-commit                                      # runs pre-commit checks locally
    publish                                         # publishes the built package to PyPI (prefer the trusted publishers method in GitHub)
    pyright                                         # runs Pyright checks locally
    serve-coverage                                  # serves the HTML coverage report at http://localhost:1313 [alias: serve]
    test python=python_version *pytest_args         # runs tests using the default dependency resolution
    test-all                                        # tests against all supported python versions and dep lower bounds (no integration tests)
    test-integration python=python_version *pytest_args # runs integration tests using the default dependency resolution
    test-integration-verbose python=python_version *pytest_args # runs integration tests in verbose mode with stdout capture; useful for debugging test failures
    test-lowest python=python_version *pytest_args  # runs tests against the lowest dependency versions
    test-verbose python=python_version *pytest_args # runs local tests in verbose mode with stdout capture; useful for debugging test failures
    update                                          # updates development dependencies and pre-commit hooks
```

Examples:

```bash
just dev-setup
just test
just test 3.12 --no-cov -k test_authentication
just pre-commit
just build
```

> [!TIP]
> If testing a python version other than the default, you can run just dev-setup
> again to reset the environment to the default version after running the tests

### Integration Testing

Integration tests need more setup. You need to deploy the Gateway and Network
components, create a test user, and set up the integration test environment:

1. Follow the Network setup instructions in the [Network README](../network/README.md);
    1. Adjust TLS according to your setup;
    2. Modify your local DNS resolution if you'd like to simulate requests to a custom
       domain;
2. Follow the Gateway instructions in the [Gateway README](../gateway/README.md); In
   summary:
    1. Deploy the Docker Compose stack;
    2. Create a MinIO user and bucket with same credentials as in `minio.env`;
3. Create a test user and API key:
    1. Create a Gateway superuser and a regular user (they may be the same);
    2. Enable their `is_approved` flag in the [admin
       panel](http://localhost:8000/admin);
    3. With the flag enabled, login as that user and create an API key for them;
    4. Copy / save the key.
4. Integration test setup:
    1. Create `tests/integration/integration.env` from its example counterpart
    2. Set the api key to the one created.
    3. Run the `just test-integration` target.

Then you can run the integration tests:

```bash
just test-integration
# runs integration tests with pytest

just test-integration-verbose
# like just test-integration, but with extra verbosity and log capture
```

### More testing options

```bash
# simple tests execution (similar to `just test`)
uv run pytest -v

# running similar tests (substring match)
uv run pytest -v -k test_authentication

# running a specific test
uv run pytest -v tests/test_usage.py::test_authentication_200_succeeds

# verbose with colored log messages (similar to `just test-verbose`)
uv run pytest -vvv --show-capture=stdout -o log_cli=true --log-cli-level=DEBUG --capture=no
```
