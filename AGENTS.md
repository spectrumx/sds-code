# AGENTS.md

## Cursor Cloud specific instructions

This monorepo contains several components (`gateway`, `sdk`, `network`, `jupyter`,
`seaweedfs`). The core product is the **Gateway** — a Django web app + REST API. The
**SDK** (`spectrumx`) is the Python client library. Everything for the Gateway runs in
Docker Compose; there is no top-level orchestrator, each component is driven from its own
directory via `just` + Docker Compose. Standard recipes are documented in
`gateway/README.md` and `gateway/justfile` (`just --list`); prefer those over duplicating
commands here.

### Docker daemon must be started manually

There is no `systemd` in this environment, so Docker does not auto-start. Before running
any Gateway/`just` command, start the daemon if it is not already running (it listens on
the default socket, and the `ubuntu` user is in the `docker` group so `sudo` is not needed
for the `docker` CLI):

```bash
pgrep dockerd >/dev/null || sudo dockerd >/tmp/dockerd.log 2>&1 &
# if the socket is not group-accessible after a fresh start:
sudo chmod 666 /var/run/docker.sock
```

### Running the Gateway stack (the end-to-end product)

From `gateway/`, the local deploy builds all images and starts the stack. Skip SeaweedFS
locally — RustFS is the primary S3 store for local/CI, and SeaweedFS is only an optional
secondary store:

```bash
cd gateway
SDS_SKIP_SFS=true ./scripts/deploy.sh local
```

The web app is served directly at <http://localhost:8000> (admin at `/admin`, API docs at
`/api/latest/docs/`, webpack dev server at <http://localhost:3000>).

`deploy.sh` is interactive by default in two places; make it non-interactive like this:

- It prompts "Is this machine a production host?" on first run. `scripts/prod-hostnames.env`
  is created before the prompt, so it is skipped on subsequent runs. To avoid it entirely,
  ensure `scripts/prod-hostnames.env` exists and redirect stdin from `/dev/null`.
- `createsuperuser` is interactive and is skipped when there is no TTY. Create a superuser
  non-interactively against the running app container instead (the user model's
  `USERNAME_FIELD` is `email`):

```bash
docker exec -e DJANGO_SUPERUSER_PASSWORD='<pw>' \
  sds-gateway-local-app \
  uv run python manage.py createsuperuser --noinput --email <email>
```

Local auth uses django-allauth with email + password (email verification is off and
self-registration is allowed), so you can also just sign up at `/accounts/login/`.

### Known non-blocking caveat: nginx health

The `sds-gateway-local-nginx` container reports `unhealthy`. This is only because its
healthcheck runs `wget http://localhost/healthz`, which resolves to IPv6 `::1` while nginx
listens on IPv4 `0.0.0.0:80`. nginx serves correctly (static files and `/healthz` return
`200` over IPv4). This does not affect local development — the Django app is reached
directly on port `8000`.

### Lint / test / build

Run from `gateway/`:

- Lint (all pre-commit hooks): `just pre-commit`
- Python tests (pytest inside the app container): `just test-py`
- JavaScript tests (jest inside the node container): `just test-js`
- Everything: `just test`

The host-side `uv` virtualenvs (in `gateway/.venv` and `sdk/.venv`) are used for lint
tooling (ruff, deptry, pyrefly) and are refreshed by the startup update script. Note that
the containers manage their own dependencies (synced on image build / container entrypoint);
re-running a host `uv sync` does not update code already running inside containers — rebuild
the relevant service (`just build <service>` / `just redeploy`) to pick up dependency
changes there.
