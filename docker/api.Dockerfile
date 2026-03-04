# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /api

ENV PYTHONUNBUFFERED=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Dependencies
COPY apps/api/pyproject.toml ./
RUN uv sync --no-dev --no-editable

# App
COPY apps/api/ .

# Final stage
FROM python:${PYTHON_VERSION}-slim AS runner

WORKDIR /api

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy venv and app from builder
COPY --from=builder /api/.venv /api/.venv
COPY --from=builder /api/app /api/app
COPY --from=builder /api/pyproject.toml /api/

ENV PATH="/api/.venv/bin:$PATH"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
