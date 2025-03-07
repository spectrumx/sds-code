# Build and manage a local deploy of the SDS Gateway - NOT PRODUCTION READY

.PHONY: all redeploy build up logs logs-once down restart

all: build up logs
redeploy: build down up logs

# Variables
COMPOSE_FILE := compose.local.yaml
ENV_FILE := .envs/local/opensearch.env

build-full:
	@echo "Pulling and building sds-gateway WITHOUT CACHE"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) pull --ignore-buildable
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) build --no-cache $(ARGS)

build:
	@echo "Pulling and building sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) pull --ignore-buildable
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) build $(ARGS)

up:
	@echo "Starting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) up -d $(ARGS)

logs:
	@echo "Showing sds-gateway logs…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) logs -f $(ARGS)

logs-once:
	@echo "Showing gateway logs once…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) logs $(ARGS)

down:
	@echo "Stopping sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) down $(ARGS)

restart:
	@echo "Restarting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) restart $(ARGS)
