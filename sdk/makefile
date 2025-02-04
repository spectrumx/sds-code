SHELL=/bin/bash

PYTHON_VERSION ?= 3.13
SUPPORTED_PYTHON_VERSIONS := 3.12 3.13
GIT_ROOT := $(shell git rev-parse --show-toplevel;)
TEST_MARKER_DEFAULT := not integration
TEST_MARKER_INTEGRATION := integration

.PHONY: all install gact pyright pre-commit test test-lowest test-verbose test-all test-integration \
	test-integration-verbose serve-coverage clean update build publish

all: install test

# SETUP
install:
	uv sync --dev --frozen
	uv run pre-commit install --install-hooks

# GITHUB ACTIONS
gact:
	# install gh-act with:
	# 	gh extension install nektos/gh-act
	echo Running GitHub Actions locally for "$(GIT_ROOT)";
	cd "$(GIT_ROOT)" && \
	gh act \
		--workflows "$(GIT_ROOT)/.github/workflows" \
		--secret-file config/secrets.env

# CODE QUALITY
pyright:
	echo Running Pyright locally for "$(GIT_ROOT)";
	cd "$(GIT_ROOT)" && \
	gh act --workflows "$(GIT_ROOT)/.github/workflows" --job pyright

pre-commit:
	uv run --dev pre-commit run --all-files

# TESTS
test:
	uv run --resolution highest -p $(PYTHON_VERSION) pytest \
		-m '$(TEST_MARKER_DEFAULT)' \
		--cov=src \
		--cov-config=pyproject.toml \
		--cov-report=term-missing:skip-covered \
		--cov-report=html \
		--cov-report=html:tests/htmlcov \
		--cov-fail-under=75 \
		tests

test-lowest:
	# Run tests against the lowest versions of dependencies to ensure compatibility
	uv run -v --resolution lowest-direct -p $(PYTHON_VERSION) pytest \
		-m "$(TEST_MARKER_DEFAULT)" \
		tests

test-verbose:
	uv run --resolution highest -p $(PYTHON_VERSION) pytest \
		-vvv \
		-m "$(TEST_MARKER_DEFAULT)" \
		--show-capture=stdout \
		-o log_cli=true \
		--log-cli-level=DEBUG \
		--capture=no

test-integration:
	echo -e "\n\t\033[33mRunning integration tests: make sure you set up the web application\033[0m"; \
	echo -e "\t\033[33mand configure 'tests/integration/integration.env'\033[0m\n"
	uv run --resolution highest -p $(PYTHON_VERSION) pytest \
		-m "$(TEST_MARKER_INTEGRATION)" \
		tests

test-integration-verbose:
	echo -e "\n\t\033[33mRunning integration tests: make sure you set up the web application\033[0m"; \
	echo -e "\t\033[33mand configure 'tests/integration/integration.env'\033[0m\n"
	uv run --resolution highest -p $(PYTHON_VERSION) pytest \
		-m "$(TEST_MARKER_INTEGRATION)" \
		-vvv \
		--capture=no \
		tests

test-all:
	echo -e "\n\t\033[34mRunning all local (non-integration) tests\033[0m\n"
	echo -e "\n\t\033[34mRunning tests against the highest dep versions and generating reports\033[0m\n"
	$(MAKE) test
	echo -e "\n\t\033[34mRunning tests against the lowest dep versions vs. all supported python versions\033[0m\n"
	for version in $(SUPPORTED_PYTHON_VERSIONS); do \
		echo -e "\n\t\033[34mRunning lower bound tests against Python $$version\033[0m\n"; \
		$(MAKE) test-lowest PYTHON_VERSION=$$version; \
	done
	echo -e "\n\t\033[34mRestoring highest dep versions\033[0m\n"
	uv sync --resolution highest --dev

check-acceptance:
	echo -e "\n\t\033[34mRunning acceptance checks using current environment \033[33m(NOT BUILT ARTIFACT)\033[0m\n"
	uv run -p $(PYTHON_VERSION) tests/e2e_examples/check_build_acceptance.py

serve-coverage:
	python -m http.server 1313 -d tests/htmlcov

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
	uv run pre-commit autoupdate

build:
	uv build
	echo -e "\n\t\033[32mRunning smoke tests on the built package\033[0m\n"
	uv run --isolated --no-project -p $(PYTHON_VERSION) --with dist/*.tar.gz tests/e2e_examples/check_build_acceptance.py
	# clean-up generated files
	rm my_spectrum_files/rf_run_*.csv && rmdir my_spectrum_files
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
