FROM docker.io/node:20-bookworm-slim

WORKDIR /app

COPY ./package.json /app
COPY ./webpack/ /app/webpack/
COPY ./sds_gateway/static/ /app/sds_gateway/static/

RUN npm install && npm cache clean --force

ENV PATH=./node_modules/.bin/:$PATH
