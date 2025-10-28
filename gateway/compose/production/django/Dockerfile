# https://hub.docker.com/_/node/tags?name=slim
FROM docker.io/node:24-trixie-slim AS client-builder

ARG APP_HOME=/app
WORKDIR ${APP_HOME}

COPY ./package.json ${APP_HOME}
RUN npm install && npm cache clean --force
COPY . ${APP_HOME}
RUN npm run build

# https://hub.docker.com/_/python/tags?name=3.13
FROM docker.io/python:3.13-slim-trixie AS python

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG BUILD_ENVIRONMENT=production
ARG APP_HOME=/app

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

# Install Rust and Cargo
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y && \
    . $HOME/.cargo/env && \
    echo 'export PATH=$HOME/.cargo/bin:$PATH' >> $HOME/.bashrc
ENV PATH="/root/.cargo/bin:${PATH}"

WORKDIR ${APP_HOME}

# https://docs.astral.sh/uv/guides/integration/docker/
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_CACHE_DIR=/opt/uv-cache/

RUN addgroup --system django \
    && adduser --system --ingroup django django

# we can delay the project dependencies installation to reduce
# the image size: it'll be cached at the compose level. If you
# wish to include them in the image, uncomment the following lines:
# COPY ./pyproject.toml ./uv.lock ${APP_HOME}/
# RUN uv sync --frozen --extra ${BUILD_ENVIRONMENT}

# copy command scripts and set exec flag
COPY --chown=django:django ./compose/production/django/entrypoint           /entrypoint
COPY --chown=django:django ./compose/production/django/start                /start
COPY --chown=django:django ./compose/production/django/celery/worker-start  /worker-start
COPY --chown=django:django ./compose/production/django/celery/flower-start  /flower-start
COPY --chown=django:django ./compose/production/django/celery/beat-start    /beat-start

RUN chmod +x /entrypoint /start /worker-start /flower-start /beat-start

# copy application code to WORKDIR
COPY --from=client-builder --chown=django:django ${APP_HOME} ${APP_HOME}
RUN chown -R django:django ${APP_HOME}

# create temp_zips directory and set permissions
RUN mkdir -p ${APP_HOME}/sds_gateway/media/temp_zips && \
    chown -R django:django ${APP_HOME}/sds_gateway/media/temp_zips && \
    find ${APP_HOME}/sds_gateway/media/temp_zips -type d -exec chmod 755 {} \;

USER django

ENTRYPOINT ["/entrypoint"]
