# GitHub Actions Ephemeral Environment

This document describes how to run the SDS Gateway stack in an ephemeral CI environment
like GitHub Actions.

## Overview

The gateway component now supports automated secret generation for ephemeral
environments. This eliminates the manual step of creating `.env` files and makes it easy
to spin up the full stack in CI.

## Quick Start

### 1. Generate CI Secrets

```bash
# In the gateway directory
just generate-secrets ci

# Or directly with the script
./scripts/generate-secrets.sh ci
```

This creates all required env files in `.envs/ci/` with safe, predictable values for
ephemeral environments.

### 2. Start the Stack

```bash
# The env-selection.sh script will detect you're in CI mode
# if you set GITHUB_ACTIONS=true or similar
just up
```

## GitHub Actions Workflow Example

Here's a minimal workflow that runs the gateway stack with all dependencies:

```yaml
name: Gateway Integration Tests

on:
  pull_request:
    paths:
      - 'gateway/**'
  push:
    branches: [master]

jobs:
  integration-test:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Install just
        uses: extractions/setup-just@v2

      - name: Generate CI secrets
        working-directory: gateway
        run: ./scripts/generate-secrets.sh ci

      - name: Start gateway stack
        working-directory: gateway
        run: |
          # Override env detection to use CI
          export COMPOSE_FILE=compose.local.yaml
          docker compose --env-file .envs/ci/opensearch.env up -d

      - name: Wait for services to be healthy
        working-directory: gateway
        run: |
          timeout 120 bash -c 'until docker compose --env-file .envs/ci/opensearch.env ps | grep -q "healthy"; do sleep 2; done'

      - name: Run migrations
        working-directory: gateway
        run: |
          docker compose --env-file .envs/ci/opensearch.env \
            run sds-gateway-local-app uv run manage.py migrate

      - name: Run tests
        working-directory: gateway
        run: |
          docker compose --env-file .envs/ci/opensearch.env \
            run sds-gateway-local-app uv run pytest

      - name: Cleanup
        if: always()
        working-directory: gateway
        run: docker compose --env-file .envs/ci/opensearch.env down -v
```

## CI Environment Values

The CI environment uses safe, deterministic values:

| Service       | Variable                            | Value                           |
| ------------- | ----------------------------------- | ------------------------------- |
| Postgres      | `POSTGRES_PASSWORD`                 | `ci-postgres-pass`              |
| MinIO         | `MINIO_ROOT_PASSWORD`               | `ci-minio-secret`               |
| MinIO         | `AWS_SECRET_ACCESS_KEY`             | `ci-minio-secret`               |
| OpenSearch    | `OPENSEARCH_INITIAL_ADMIN_PASSWORD` | `CiAdmin123!`                   |
| OpenSearch    | `OPENSEARCH_PASSWORD`               | `CiDjango123!`                  |
| Celery Flower | `CELERY_FLOWER_PASSWORD`            | `ci-flower-pass`                |
| SVI           | `SVI_SERVER_API_KEY`                | `ci-svi-api-key-...` (40 chars) |

These values are **not secure** but are acceptable for ephemeral CI environments that
are destroyed after each run.

## Customizing for Your CI

### Using a Different CI System

If you're not using GitHub Actions, you can still use the same approach:

```bash
# GitLab CI, CircleCI, etc.
./scripts/generate-secrets.sh ci
docker compose -f compose.local.yaml --env-file .envs/ci/opensearch.env up -d
```

### Using Production-like Secrets in CI

If you need production-like random secrets even in CI:

```bash
# Generate random secrets instead of deterministic ones
./scripts/generate-secrets.sh local
# Then use .envs/local/ in your CI compose commands
```

### Force Regeneration

If secrets already exist and you want to regenerate them:

```bash
./scripts/generate-secrets.sh --force ci
```

## Local Development

For local development, generate local secrets with random values:

```bash
just generate-secrets local
# or
./scripts/generate-secrets.sh local
```

Then customize `.envs/local/*.env` as needed (e.g., add Auth0 credentials, Sentry DSN,
etc.).

## Production Deployment

For production:

```bash
just generate-secrets production
# or
./scripts/generate-secrets.sh production
```

**Important**: Review and customize all `.envs/production/*.env` files before deploying.
The generated secrets are random but you should:

1. Set proper Auth0 credentials
2. Configure Sentry DSN if using
3. Review all other optional variables
4. Store secrets securely (e.g., in your secrets manager)

## Troubleshooting

### Services fail to start

Check that all env files were generated:

```bash
ls -la .envs/ci/
# Should show: django.env, minio.env, opensearch.env, postgres.env
```

### Secrets not populated

If you see placeholder values like `POSTGRES_PASSWORD=your-specific-password`, regenerate
with `--force`:

```bash
./scripts/generate-secrets.sh --force ci
```

### Permission errors with OpenSearch

Make sure `UID` and `GID` in `.envs/ci/opensearch.env` match your user (or use 1000:1000
for CI).

## See Also

- [../scripts/generate-secrets.sh](../scripts/generate-secrets.sh) - The secrets
  generator script
- [../compose.local.yaml](../compose.local.yaml) - Local compose configuration
- [../.envs/example/](../.envs/example/) - Example env files used as templates
