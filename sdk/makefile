SHELL=/bin/bash

PYTHON_VERSION ?= 3.13
SUPPORTED_PYTHON_VERSIONS := 3.12 3.13
GIT_ROOT := $(shell git rev-parse --show-toplevel;)

all: install test

# SETUP
install:
	uvx pre-commit install --install-hooks
	uv sync --dev --frozen

# GITHUB ACTIONS
gact:
	# install gh-act with:
	# 	gh extension install nektos/gh-act
	echo Running GitHub Actions locally for "$(GIT_ROOT)";
	cd "$(GIT_ROOT)" && \
	gh act \
		--workflows "$(GIT_ROOT)/.github/workflows" \
		--secret-file config/secrets.env

pyright:
	echo Running Pyright locally for "$(GIT_ROOT)";
	cd "$(GIT_ROOT)" && \
	gh act --workflows "$(GIT_ROOT)/.github/workflows" --job pyright

# TESTS
test:
	uv run --resolution highest -p $(PYTHON_VERSION) pytest \
		--cov=src \
		--cov-config=pyproject.toml \
		--cov-report=term-missing:skip-covered \
		--cov-report=html \
		--cov-report=html:tests/htmlcov \
		--cov-fail-under=75 \
		tests
test-lowest:
	# Run tests against the lowest versions of dependencies to ensure compatibility
	uv run --resolution lowest-direct -p $(PYTHON_VERSION) pytest tests
test-verbose:
	uv run -p $(PYTHON_VERSION) pytest -vvv --show-capture=stdout -o log_cli=true --log-cli-level=DEBUG --capture=no
test-all:
	echo -e "\n\t\033[34mRunning tests against the highest dep versions and generating reports\033[0m\n"
	$(MAKE) test
	echo -e "\n\t\033[34mRunning tests against the lowest dep versions vs. all supported python versions\033[0m\n"
	for version in $(SUPPORTED_PYTHON_VERSIONS); do \
		echo -e "\n\t\033[34mRunning lower bound tests against Python $$version\033[0m\n"; \
		$(MAKE) test-lowest PYTHON_VERSION=$$version; \
	done
	echo -e "\n\t\033[34mRestoring highest dep versions\033[0m\n"
	uv sync --resolution highest --dev

serve-coverage:
	python -m http.server 8000 -d tests/htmlcov

# CLEANUP
clean:
	rm -rf \
		.tox .coverage \
		.pytest_cache .python-version .cache dist \
		.venv .eggs .eggs/ \
		./**/*.py.cover \
		*.egg-info *.egg-info/

# UPDATE
update:
	uv sync --upgrade
	uvx pre-commit autoupdate

build:
	uv build
	echo -e "\n\t\033[32mBuilt package:\033[0m\n"
	tar -tvf dist/*.tar.gz | sort -k6
	echo -e "\n\t\033[34mTo publish it, run 'make publish'.\033[0m\n\n"

# PUBLISH
publish:
	@if [ ! -d dist ]; then \
		echo "Run 'make build' first."; \
		exit 1; \
	fi
	@if [ ! -f config/secrets.env ]; then \
		echo "Error: config/secrets.env does not exist."; \
		exit 1; \
	fi
	export UV_PUBLISH_TOKEN=$$(grep PYPI_API_TOKEN config/secrets.env | cut -d '=' -f2); \
	uv publish
