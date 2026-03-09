---
name: agent-workflow
description: Orchestrator workflow for agents working in this repo. Read this first; it tells you which skills to load and how to operate (checks, docs, conventions).
---

# Agent workflow (Renly repo)

## 1. Load skills first

Before doing substantive work, read and apply the relevant skills so your changes follow repo conventions:

- **api-layering** — Where to create files in `apps/api` (routers, services, repositories, schemas, etc.) and request flow.
- **api-methods** — Method order and comments in API code.
- **web-structure** — Where to create pages, components, and config in `apps/web`; directory layout.
- **web-components-pages** — How to add a page or component; colocation; order and style; comments.

Use **api-\*** skills when touching the backend; **web-\*** when touching the frontend. Use both when a change spans API and web.

## 2. Lints and checks before commit

Before committing (or suggesting a commit), ensure lints and checks pass. The repo runs them on every commit via Husky (lint-staged, `pnpm check:api`, `pnpm check:web`), so the tree should stay green — but don’t leave broken state or rely on “fix later.” If you’re about to commit, run from repo root:

- `pnpm lint` (and fix if needed)
- `pnpm format:check` (or `pnpm format` to fix)
- `pnpm check:api`
- `pnpm check:web`

So: no strict obligation to run these manually every time, since pre-commit runs them; the obligation is not to commit code that would fail these checks.

## 3. Keep docs current (READMEs, then skills)

Docs describe **how things work now**, not “what we changed” (no changelog-style “this works like this now” in READMEs).

- **On every change:** If your change affects setup, structure, a specific flow or how to run/check something, update the relevant README (root, `apps/api`, `apps/web`) so it still says how things work. One source of truth; no drift.
- **When to update skills:** Less often. Update a skill when you change a **convention** or **structure** (e.g. new layer, new place for components, new comment style). If you only added a feature following existing conventions, you usually don’t need to edit a skill.

## 4. Other habits

- **Scope:** Know which app you’re in (`apps/api` vs `apps/web`). Use the right tooling (e.g. `uv` in API, `pnpm --filter web` for web).
- **After big refactors:** Run `pnpm check:api` and `pnpm check:web` once to catch import/model/type errors before the user hits pre-commit.
- **Hooks:** Don’t remove or weaken pre-commit checks without a clear reason; they’re there so CI and local stay aligned.
- **Paths and config:** API uses `app.*` and `apps/api` as cwd; web uses `@/` aliases and `config/routes.ts`. Follow the structure and skills so new code lands in the right place.
- **Empty folders:** When adding the first real file to a folder that only had a `.gitkeep`, remove the `.gitkeep` so the folder is no longer “empty” and the new file is the only content.
