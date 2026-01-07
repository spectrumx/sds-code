# SpectrumX Data System | Gateway

Metadata management and web interface for SDS.

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

+ [SpectrumX Data System | Gateway](#spectrumx-data-system--gateway)
    + [System requirements](#system-requirements)
    + [Development setup](#development-setup)
    + [Quick deploy](#quick-deploy)
    + [Just recipes](#just-recipes)
    + [More SDS Gateway docs](#more-sds-gateway-docs)

> [!TIP]
> Deploying SDS in production? Start with the [`network`](../network/README.md) component.

## System requirements

The recommended operating system is a Linux distribution.

Make sure you have the following binaries available:

+ [`docker`](https://docs.docker.com/get-docker/) - container runtime
+ [`just`](https://github.com/casey/just) - command runner
+ [`uv`](https://docs.astral.sh/uv/getting-started/installation/) - python package and project manager

## Development setup

Run the following `just` recipe and install any missing dependencies:

```bash
just dev-setup
```

## Quick deploy

After cloning this repo, follow the steps below:

```bash
# for a local (dev / evaluation) environment:
./scripts/deploy.sh local

# for ci:
./scripts/deploy.sh ci

# for production:
./scripts/deploy.sh production
```

Then follow the steps that are [not automated for a first-time setup](./docs/detailed-deploy.md#first-deployment-not-automated).

This _should_ leave you with the application running using default configurations. If
that doesn't happen, feel free to open an issue or reach out for help.

## Just recipes

We are using [Just](https://github.com/casey/just#installation/) as a command runner to
simplify common tasks. Here's a quick lookup of available commands:

```bash
just --list
```

```bash
Available recipes:
    build *args                     # pulls and rebuild the compose services with optional args
    build-full *args                # pulls and rebuilds from scratch without cache
    clean                           # removes ephemeral files, like python caches and test coverage reports
    dc +args                        # runs a generic docker compose command e.g. `just dc ps`
    dev-setup                       # sets up the development environment
    down *args                      # stops and remove compose services; args are passed to compose down
    env                             # prints currently selected environment, for debugging and validation purposes
    generate-secrets env_type *args # generates environment secrets for local/production/ci environments
    logs *args                      # streams logs until interrupted (tails 10k lines); args are passed to compose logs
    logs-once *args                 # prints all recent logs once; args are passed to compose logs
    pre-commit                      # runs the pre-commit hooks with dev dependencies
    redeploy services=''            # rebuilds then restarts services and shows logs
    restart *args                   # restarts running compose services
    serve-coverage                  # serves pytest coverage HTML locally
    snapshot                        # captures a snapshot of the configured environment
    test *args                      # runs all tests (python and javascript); args are passed to pytest
    test-js *args                   # runs javascript tests inside the app container
    test-py *args                   # validates templates and runs pytest inside the app container
    up *args                        # starts services in detached mode; if env is local, starts process to watch files [alias: run]
    update                          # upgrades pre-commit hooks and gateway dependencies to their latest compatible versions [alias: upgrade]
    uv +args                        # shorthand for 'uv' commands (e.g. `just uv run manage.py migrate`)
    watch *args                     # watch file changes when in local env mode
```

## More SDS Gateway docs

+ [Setting up a dev environment](./docs/detailed-deploy.md#development-environment)
+ Production
    + [Detailed production deploy instructions](./docs/detailed-deploy.md#production-deploy)
    + [Production backups](./docs/dev-notes.md#production-backups)
+ Others
    + [OpenSearch Query Tips](./docs/detailed-deploy.md#opensearch-query-tips)
    + [Handling migration conflicts](./docs/dev-notes.md#handling-migration-conflicts)
