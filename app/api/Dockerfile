FROM python:3.13-slim AS base
WORKDIR /app

RUN pip install --no-cache-dir uv

COPY app/pyproject.toml ./
RUN uv sync --no-dev

FROM base AS dev
RUN uv sync

FROM base AS prod
COPY app/ ./
CMD ["uv", "run", "python", "-m", "api"]
