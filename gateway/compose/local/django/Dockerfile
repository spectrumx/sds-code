# https://hub.docker.com/_/node/tags?name=slim
FROM ghcr.io/pnpm/pnpm:11 AS client-builder

RUN pnpm runtime set node 24 -g && cp /pnpm/bin/node /usr/local/bin/node && rm /pnpm/bin/node

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

COPY ./package.json ${APP_HOME}
COPY ./pnpm-lock.yaml ${APP_HOME}
COPY ./pnpm-workspace.yaml ${APP_HOME}
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile
COPY . ${APP_HOME}
RUN pnpm run build

# https://hub.docker.com/_/python/tags?name=3.13
FROM docker.io/python:3.13-slim-trixie AS python

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG BUILD_ENVIRONMENT=local
ARG APP_HOME=/app
ARG GIT_COMMIT=none

ENV BUILD_ENV=${BUILD_ENVIRONMENT}
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
    # better utils if we need to run a shell in the container
    git bash-completion nano ssh htop \
    rsync net-tools wget curl jq nmap \
    # psycopg build
    build-essential \
    libpq-dev \
    # translations dependencies
    gettext \
    # hdf5 deps for digital-rf
    hdf5-tools \
    libhdf5-dev \
    libhdf5-serial-dev \
    python3-dev \
    python3-h5py \
    # purge cache to reduce image size
    && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
    && rm -rf /var/lib/apt/lists/*

# install rust toolchain for the `blake3` package
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    . $HOME/.cargo/env && \
    echo 'export PATH=$HOME/.cargo/bin:$PATH' >> $HOME/.bashrc
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR ${APP_HOME}

# https://docs.astral.sh/uv/guides/integration/docker/
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_CACHE_DIR=/opt/uv-cache/
ENV UV_PROJECT_SEED=/opt/uv-venv-seed/
ENV UV_PROJECT_ENVIRONMENT=/opt/uv-venv/

RUN mkdir -p /opt/uv-cache/ /opt/uv-venv/ /opt/uv-venv-seed/

# Bake third-party dependencies, then the project, into a seed virtualenv.
COPY ./pyproject.toml ./uv.lock ${APP_HOME}/
RUN UV_PROJECT_ENVIRONMENT=${UV_PROJECT_SEED} uv sync --frozen --no-install-project --extra ${BUILD_ENVIRONMENT}

# "entrypoint" only has a production version
COPY ./compose/production/django/entrypoint         /entrypoint

# copy command scripts and set exec flag
COPY ./compose/local/django/start                   /start
COPY ./compose/local/django/celery/flower-start     /flower-start
COPY ./compose/local/django/celery/worker-start     /worker-start
COPY ./compose/local/django/celery/beat-start       /beat-start
RUN chmod +x /entrypoint /start /worker-start /flower-start /beat-start

# copy application code to WORKDIR
COPY . ${APP_HOME}
RUN UV_PROJECT_ENVIRONMENT=${UV_PROJECT_SEED} uv sync --frozen --extra ${BUILD_ENVIRONMENT}

# Generate version.json with baked-in commit hash (passed as build ARG)
RUN echo "{\"commit\":\"${GIT_COMMIT}\",\"version\":\"${GIT_COMMIT}\",\"build_date\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\"}" > ${APP_HOME}/version.json

ENTRYPOINT ["/entrypoint"]
