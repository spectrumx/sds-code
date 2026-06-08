FROM ghcr.io/pnpm/pnpm:11

RUN pnpm runtime set node 24 -g && cp /pnpm/bin/node /usr/local/bin/node && rm /pnpm/bin/node

WORKDIR /app

# Pin the store directory so it's consistent between docker build
# (with cache mount at /pnpm/store) and docker compose run (without cache mount).
# Without this, pnpm 11 defaults to a project-local store (/app/.pnpm-store/v11)
# which conflicts with the symlinks in node_modules linked from /pnpm/store/v11.
RUN pnpm config set store-dir /pnpm/store --global

COPY ./package.json /app
COPY ./pnpm-lock.yaml /app
COPY ./pnpm-workspace.yaml /app
COPY ./webpack/ /app/webpack/
COPY ./sds_gateway/static/ /app/sds_gateway/static/

RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

ENV PATH=./node_modules/.bin/:$PATH
