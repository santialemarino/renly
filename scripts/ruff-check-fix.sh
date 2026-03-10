#!/usr/bin/env bash
# Used by lint-staged for apps/api/**/*.py. Receives paths relative to repo root (e.g. apps/api/app/foo.py).
# Strips apps/api/ and runs ruff from apps/api so paths are correct.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CD="apps/api"
args=()
for f in "$@"; do
  args+=("${f#apps/api/}")
done
cd "$ROOT/$CD" && uv run ruff check --fix "${args[@]}"
