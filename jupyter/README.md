# SDS Jupyter Component

This directory contains the JupyterHub deployment for the SDS platform.

For build, deployment, and management commands, refer to the recipes in the `justfile`.
Environment selection and Docker Compose orchestration are handled via the provided
scripts and configuration files.

```bash
just --list
```

```bash
Available recipes:
    all                # builds, starts, and shows logs for all services
    build args=''      # builds the docker compose services
    build-full args='' # builds the docker compose services without cache
    dc +args=''        # runs arbitrary docker compose commands
    down args=''       # stops the docker compose services
    env                # displays selected environment information
    logs args=''       # shows and follows docker compose logs
    logs-once args=''  # shows docker compose logs once
    redeploy           # redeploys by building, stopping, starting, and showing logs
    restart args=''    # restarts the docker compose services
    up args=''         # starts the docker compose services [alias: run]
```

## Getting Started

Make sure our environment is properly set:

```bash
rsync -aP ./.envs/example ./.envs/local     # or ./.envs/production
```

Edit the files in `./.envs/local` accordingly. There are comments to guide you.

Use the following one-liner to automatically generate a secret you can paste in password
or key fields:

```bash
openssl rand -hex 32
```

Check your env looks correct:

```bash
less "./.envs/local/jupyterhub.env"
just env
```

Then, build and start the JupyterHub service:

```bash
just redeploy
```

And navigate to `http://localhost:8888` (or `http://localhost:18888` for production).

Your default user is `admin` and the password is what you set in the env file as
`JUPYTERHUB_DUMMY_PASSWORD`. The default when missing is `admin`. Use a less predictable
password in production.
