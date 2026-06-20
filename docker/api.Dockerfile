# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.13

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /api

ENV PYTHONUNBUFFERED=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Build the venv against the image's own Python (3.13). Without this, uv may download a managed
# interpreter that lives outside /api/.venv and is therefore not copied into the runner stage,
# leaving the venv's python symlink dangling so uvicorn can't start.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system

# Dependencies (README is required because pyproject's `readme` field is read when building the project)
COPY apps/api/pyproject.toml apps/api/README.md ./
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
