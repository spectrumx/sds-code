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
	# 	gh extension install nektos/gh-act
	git_root=$$(git rev-parse --show-toplevel);
	echo Running GitHub Actions locally for "${git_root}";
	cd "$$git_root"
	gh act \
		--workflows "$$git_root"/.github/workflows \
		--secret-file config/secrets.env

# TESTS
test:
	uv run -p $(PYTHON_VERSION) pytest \
		--cov=src \
		--cov-config=pyproject.toml \
		--cov-report=term-missing:skip-covered \
		--cov-report=html \
		--cov-report=html:tests/htmlcov \
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
		./**/*.py.cover \
		*.egg-info *.egg-info/

# UPDATE
update:
	uv sync --upgrade
	uvx pre-commit autoupdate

build:
	uv build
	echo -e "\n\t\033[32mBuilt package:\033[0m\n"
	tar -tvf dist/*.tar.gz
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
	export UV_PUBLISH_TOKEN=$$(grep PYPI_API_TOKEN config/secrets.env | cut -d '=' -f2)
	uv publish
