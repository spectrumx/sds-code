FROM docker.io/python:3.14-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app/federation
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build context is repo root (compose: context: ..).
COPY common /app/common
COPY federation/pyproject.toml federation/uv.lock ./
COPY federation/sds_federation ./sds_federation
RUN uv sync --frozen --no-dev

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "sds_federation.main:app", "--host", "0.0.0.0", "--port", "8000"]
