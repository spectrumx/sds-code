# Build and manage a local deploy of the SDS Gateway - NOT PRODUCTION READY

# Variables
COMPOSE_FILE := compose.local.yaml
ENV_FILE := .envs/production/opensearch.env

.PHONY: all redeploy build up logs logs-once down restart

all: build up logs
redeploy: build down up logs

build:
	@echo "Pulling and building sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) pull --ignore-buildable
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) build

up:
	@echo "Starting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) up -d

logs:
	@echo "Showing sds-gateway logs…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) logs -f

logs-once:
	@echo "Showing gateway logs once…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) logs

down:
	@echo "Stopping sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) down

restart:
	@echo "Restarting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) restart
