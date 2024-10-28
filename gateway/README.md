# SpectrumX Data System Gateway

Control plane, metadata management, and web interface for SDS

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Development

### Installation

System dependencies

```bash
# dev bindings for python and postgres
sudo apt install python3-dev libpq-dev # on ubuntu
sudo dnf install python3-devel postgresql-devel # on RHEL

# get psql, createdb, etc.
sudo apt install postgresql-client # for psql
sudo dnf install postgresql # for psql
```

Python dependencies

`pip` can be used, but the easiest and fastest way is to use `uv` ([installing `uv`](https://docs.astral.sh/uv/getting-started/installation/)). If you still want to use `pip`, consider the compatible and faster alternative `uv pip` (e.g. `alias pip=uv pip`).

```bash
uv sync --frozen --extra local
# --frozen does not upgrade the dependencies
# --extra local installs the required dependencies + 'local' ones (for local development)
```

> [!NOTE]
> When using `uv`, all base, local, and production dependencies are described in the `pyproject.toml` file.
>
> If you're using `pip`, refer to the `requirements/` directory.

Install pre-commit hooks to automatically run linters, formatters, etc. before committing:

```bash
uv run pre-commit install
```

## Deployment

```bash
rsync -aP ./.envs/example ./.envs/local
# manually set the secrets in .envs/local/*.env files
```

Docker deployment recommended:

```bash
docker compose -f compose.local.yaml up
```

After the `docker compose up` command, generate static files:

```bash
docker exec -it sds_gateway_local_node bash -c 'webpack --config webpack/dev.config.js'
# check this location for the generated files:
tree sds_gateway/static/webpack_bundles/
# or
http://localhost:3000/webpack-dev-server
```

Make Django migrations and run them:

```bash
docker exec -it sds_gateway_local_django python manage.py makemigrations
docker exec -it sds_gateway_local_django python manage.py migrate
```
