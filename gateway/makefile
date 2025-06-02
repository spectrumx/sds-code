# Build and manage a local deploy of the SDS Gateway - NOT PRODUCTION READY

.PHONY: all redeploy build build-full up logs logs-once down restart test

all: build up logs
redeploy: build down up logs

# variables for local (dev) deployment
APP_CONTAINER := sds-gateway-local-app
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

pre-commit:
	uv run --dev pre-commit run --all-files

restart:
	@echo "Restarting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) restart $(ARGS)

serve-coverage:
	@echo "Serving coverage reports"
	@COMPOSE_FILE=$(COMPOSE_FILE) uv run -m http.server 1313 -d ./htmlcov

test:

	@# @echo "Validating templates"
	@# @COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) run $(APP_CONTAINER) python manage.py validate_templates

	@echo "Running tests"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) run $(APP_CONTAINER) pytest $(ARGS)

	@# Django's test runner: obsolete, subset of pytest tests, left as reference.
	@# @COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) run $(APP_CONTAINER) python manage.py test --no-input --force-color --verbosity 0
