# Build and manage a local deploy of the jupyter component - LOCAL DEV ONLY, NOT PRODUCTION

.PHONY: all redeploy build build-full up logs logs-once down pre-commit restart \
	serve-coverage test update

all: build up logs
redeploy: build down up logs

# variables for local (dev) deployment
COMPOSE_FILE := compose.local.yaml
ENV_FILE := .envs/local/jupyterhub.env

build:
	@docker network create "sds-jupyter-local-net-clients" || true
	@echo "Pulling and building sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) pull --ignore-buildable
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) build $(ARGS)

up:
	@echo "Starting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) up -d --remove-orphans $(ARGS)

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
