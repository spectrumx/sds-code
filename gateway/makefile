# Build and manage a local deploy of the SDS Gateway - NOT PRODUCTION READY

.PHONY: all redeploy build build-full up logs logs-once down pre-commit restart \
	serve-coverage test update

all: build up logs
redeploy: build down up logs

# variables for local (dev) deployment
APP_CONTAINER := sds-gateway-local-app
COMPOSE_FILE := compose.local.yaml
ENV_FILE := .envs/local/opensearch.env
ENV := local
LOG_DIR := ./logs/snapshots
LOG_FILE := "$(LOG_DIR)/$(ENV)-snapshot-$(shell date +%Y-%m-%d_%H-%M-%S).log"

build-full:
	@echo "Pulling and building sds-gateway WITHOUT CACHE"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) pull --ignore-buildable
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) build --no-cache $(ARGS)

build:
	@echo "Pulling and building sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) pull --ignore-buildable
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) build $(ARGS)

clean:
	@removed_count=$$(rm -rfv '.pytest_cache' '.ruff_cache' '__pycache__' | wc -l); \
	echo "Removed $${removed_count} entries"

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

pre-commit:
	uv run --dev pre-commit run --all-files

restart:
	@echo "Restarting sds-gateway"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) restart $(ARGS)

serve-coverage:
	@echo "Serving coverage reports"
	@COMPOSE_FILE=$(COMPOSE_FILE) python -m http.server 1313 -d ./htmlcov

snapshot:
	@echo "Creating a snapshot of '$(ENV)' data"
	@mkdir -p $(LOG_DIR)
	./scripts/create-snapshot.sh $(ENV) 2>&1 | tee $(LOG_FILE)
	@echo "Snapshot created. See '$(LOG_FILE)'"
test:

	@echo "Validating templates"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) run $(APP_CONTAINER) uv run manage.py validate_templates

	@echo "Running tests"
	@COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) run $(APP_CONTAINER) uv run pytest $(ARGS)

	@# Django's test runner: obsolete, subset of pytest tests, left as reference.
	@# @COMPOSE_FILE=$(COMPOSE_FILE) docker compose --env-file $(ENV_FILE) run $(APP_CONTAINER) uv run manage.py test --no-input --force-color --verbosity 0

update:
	@# uv sync --upgrade # re-enable when uv integration is done
	uv run pre-commit autoupdate
