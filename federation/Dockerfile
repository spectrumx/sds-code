FROM docker.io/python:3.13-slim-trixie

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./
RUN uv sync --no-dev

COPY sds_federation ./sds_federation

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "sds_federation.main:app", "--host", "0.0.0.0", "--port", "8000"]
