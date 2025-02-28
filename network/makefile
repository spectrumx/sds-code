# Build and manage a local deploy of the SDS Network - NOT PRODUCTION READY

# Variables
COMPOSE_FILE := compose.yaml

.PHONY: all redeploy build up logs logs-once down restart

all: build up logs
redeploy: build down up logs

build:
	@echo "Pulling and building sds-network…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose pull
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose build

up:
	@echo "Starting sds-network…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose up -d

logs:
	@echo "Showing sds-network logs…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose logs -f

logs-once:
	@echo "Showing sds-network logs once…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose logs

down:
	@echo "Stopping sds-network…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose down

restart:
	@echo "Restarting sds-network…"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose restart
