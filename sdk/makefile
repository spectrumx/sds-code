SHELL=/bin/bash

PYTHON_VERSION ?= 3.13

all: install test

# SETUP
install:
	uvx pre-commit install --install-hooks
	uv sync --dev --frozen

# GITHUB ACTIONS
gact:
	# install gh-act with:
	# gh extension install nektos/gh-act
	gh act --workflows .github/workflows --secret-file config/secrets.env

# TESTS
test:
	uv run -p $(PYTHON_VERSION) pytest \
		--cov=src \
		--cov-config=pyproject.toml \
		--cov-report=term-missing:skip-covered \
		--cov-report=html \
		--cov-report=html:tests/htmlcov \
		--cov-report=annotate \
		--cov-fail-under=75 \
		tests
test-verbose:
	uv run -p $(PYTHON_VERSION) pytest -vvv --show-capture=stdout -o log_cli=true --log-cli-level=DEBUG --capture=no
test-all:
	uv run -p $(PYTHON_VERSION) tox run -e "python${PYTHON_VERSION}"
	uv run -p $(PYTHON_VERSION) tox run -e "python${PYTHON_VERSION}"

serve-coverage:
	python -m http.server 8000 -d tests/htmlcov

# CLEANUP
clean:
	rm -rf \
		.tox .coverage \
		.pytest_cache .python-version .cache dist \
		.venv .eggs .eggs/ \
		*.egg-info *.egg-info/

# UPDATE
update:
	uv sync --upgrade
	uvx pre-commit autoupdate

# PUBLISH
publish:
	@if [ ! -f config/secrets.env ]; then \
		echo "Error: config/secrets.env does not exist."; \
		exit 1; \
	fi
	export UV_PUBLISH_TOKEN=$$(grep PYPI_API_TOKEN config/secrets.env | cut -d '=' -f2)
	uv build
	uv publish
