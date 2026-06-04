FROM ghcr.io/pnpm/pnpm:11

RUN pnpm runtime set node 24 -g && cp /pnpm/bin/node /usr/local/bin/node && rm /pnpm/bin/node

WORKDIR /app

COPY ./package.json /app
COPY ./pnpm-lock.yaml /app
COPY ./pnpm-workspace.yaml /app
COPY ./webpack/ /app/webpack/
COPY ./sds_gateway/static/ /app/sds_gateway/static/

RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

ENV PATH=./node_modules/.bin/:$PATH
