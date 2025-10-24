FROM docker.io/node:20-bookworm-slim

WORKDIR /app

COPY ./package.json /app

RUN npm install && npm cache clean --force

COPY . /app

ENV PATH=./node_modules/.bin/:$PATH
