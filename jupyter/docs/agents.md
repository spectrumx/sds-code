# JupyterHub Agent Documentation

## Purpose

JupyterHub deployment for SDS: spawns per-user notebook containers with spectrumx SDK access via custom Docker spawner.

## Architecture

- **Base image**: `quay.io/jupyterhub/jupyterhub:<version>` (JUPYTERHUB_VERSION arg)
- **Spawner**: Custom `MyDockerSpawner` → `dockerspawner.DockerSpawner` subclass
- **Auth**: Auth0OAuthenticator in prod; `DummyAuthenticator(admin=admin)` locally
- **Notebook image**: `quay.io/jupyter/base-notebook:latest` (DOCKER_NOTEBOOK_IMAGE env)
- **Lab interface**: JupyterLab via `jupyter-labhub` command + `JUPYTER_ENABLE_LAB=yes`
- **Idle culling**: `jupyterhub-idle-culler` service
- **DB**: SQLite at `/data/jupyterhub.sqlite`
- **Cookie secret**: Generated on build, stored at `/data/jupyterhub_cookie_secret` (600 perms)

## Key Configuration (`jupyterhub_config.py`)

- `hub_connect_ip` → container name (env-driven)
- `hub_ip/port` → bound to container interface
- `notebook_dir` → `/home/jovyan/work`
- All other settings (limits, timeouts, active_server_limit, cpu/mem limits) are environment-specific and vary by deployment

### MyDockerSpawner overrides

- Sets `CHOWN_HOME=yes`, `CHOWN_HOME_OPTS=-R`, `NB_GROUP=nb_users`
- Post-start: `pip install ipywidgets spectrumx`
- Network prefix: `sds-jupyter-local_` + `DOCKER_NETWORK_NAME`
- Volume mounts: `{username}` named volume → `/home/jovyan/work`; `sample_scripts/` → `/home/jovyan/work/sample_scripts` (ro)
- Prefix for user containers: `sds-jupyter-user`

Docker socket `/var/run/docker.sock` bind-mounted ro into hub (but `sudo` granted for chown/chmod).

## Deployment

- Local compose: `compose.local.yaml`
- Prod compose: `compose.production.yaml`
- Hub service image: `sds-jupyter-local`, port `8888:8000` (Traefik reverse proxy)
- Traefik labels configured for `/notebook` prefix strip on `sds-dev.crc.nd.edu`
- Env file: `.envs/local/jupyterhub.env`
- Networks: `sds-jupyter-local-net-clients` (bridge, alias `jupyterhub`)

## Directory Structure

- `compose/local/` → local dev compose files + Dockerfile
- `compose/production/` → prod compose files + Dockerfile + jupyterhub_config override
- `scripts/` → deployment utilities (`env-selection.sh`, `prod-hostnames.env`)
- `.envs/local/` → local env vars
- `.envs/example/` → env var template

## Key Files

| Path | Purpose |
|--|-|
| `compose.local.yaml` | Local compose stack definition |
| `compose.production.yaml` | Production compose stack |
| `compose/local/jupyter/Dockerfile` | Hub image build — installs docker.io, sudo, curl; creates users/groups |
| `compose/production/jupyter/Dockerfile` | Prod hub Dockerfile (same base + chown fix) |
| `compose/local/jupyter/jupyterhub_config.py` | Local dev Hub config + spawner override |
| `compose/production/jupyter/jupyterhub_config.py` | Prod-specific Hub config override |
| `scripts/env-selection.sh` | Staging env file selector (local vs prod) |
| `scripts/prod-hostnames.env` | Production hostname overrides |
| `.envs/local/jupyterhub.env` | Local environment variables |
| `.envs/example/jupyterhub.env` | Template for all required env vars |
