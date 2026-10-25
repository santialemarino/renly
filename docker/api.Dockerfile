# syntax=docker/dockerfile:1

ARG PYTHON_VERSION=3.14

FROM python:${PYTHON_VERSION}-slim AS builder

WORKDIR /api

ENV PYTHONUNBUFFERED=1

# Install uv, pinned so the tool that reads uv.lock is the same on every build.
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv

# Build the venv against the image's own Python. Without this, uv may download a managed
# interpreter that lives outside /api/.venv and is therefore not copied into the runner stage,
# leaving the venv's python symlink dangling so uvicorn can't start.
ENV UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system

# Dependencies, installed exactly as uv.lock pins them (README is required because pyproject's `readme`
# field is read when building the project). --locked installs from the lockfile without re-resolving, so
# the image runs the versions CI tested, and fails the build when uv.lock is out of step with
# pyproject.toml (--frozen would install the stale lock silently).
COPY apps/api/pyproject.toml apps/api/uv.lock apps/api/README.md ./
RUN uv sync --locked --no-dev --no-editable

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
# Shell form so $PORT (injected by many container hosts) is honored, defaulting to 8000; `exec`
# replaces the shell so uvicorn stays PID 1 and receives SIGTERM for graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
