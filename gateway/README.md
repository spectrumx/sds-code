# SpectrumX Data System Gateway

Control plane, metadata management, and web interface for SDS

[![Built with Cookiecutter Django](https://img.shields.io/badge/built%20with-Cookiecutter%20Django-ff69b4.svg?logo=cookiecutter)](https://github.com/cookiecutter/cookiecutter-django/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

## Development

### Installation

```bash
sudo apt install python3-dev libpq-dev # on ubuntu
sudo dnf install python3-devel postgresql-devel # on RHEL
```

`pip` can be used, but the easiest and fastest way is to use `uv` ([installing `uv`](https://docs.astral.sh/uv/getting-started/installation/)):

```bash
uv sync --frozen --extra local
# --frozen does not upgrade the dependencies
# --extra local installs the required dependencies + 'local' ones (for local development)
```

> [!NOTE]
> When using `uv`, all base, local, and production dependencies are described in the `pyproject.toml` file.
>
> If you're using `pip`, refer to the `requirements/` directory.

## Deployment

### Docker

TBD
