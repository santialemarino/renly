---
name: agent-workflow
description: Orchestrator workflow for agents working in this repo. Read this first; it tells you which skills to load and how to operate (checks, docs, conventions).
---

# Agent workflow (Renly repo)

## 1. Load skills first

Before doing substantive work, read and apply the relevant skills so your changes follow repo conventions:

- **api-layering** — Where to create files in `apps/api` (routers, services, repositories, schemas, etc.) and request flow.
- **api-methods-entities** — Method order, comments, and entity conventions (schemas, models, domain) in API code.
- **web-structure** — Where to create pages, components, and config in `apps/web`; directory layout.
- **web-components-pages** — How to add a page or component; colocation; order and style; comments.

Use **api-\*** skills when touching the backend; **web-\*** when touching the frontend. Use both when a change spans API and web.

- **commit** — Commit message format, types, and staging rules. Load when creating a commit.
- **pr-format** — PR title, body, branch name, and label conventions. Load when creating a pull request.
- **testing** — Where tests live, how to run them, what to cover. Load when writing or running tests.
- **e2e-testing** — End-to-end browser testing with Playwright in `apps/web`. Load when writing or running E2E tests, or when using `playwright-cli` to verify a feature during implementation.

## 2. Lints and checks before commit

Before committing (or suggesting a commit), ensure lints and checks pass. The repo runs them on every commit via Husky (lint-staged, `pnpm check:api`, `pnpm check:web`), so the tree should stay green — but don’t leave broken state or rely on “fix later.” If you’re about to commit, run from repo root:

- `pnpm lint` (and fix if needed)
- `pnpm format:check` (or `pnpm format` to fix)
- `pnpm check:api`
- `pnpm check:web`
- `pnpm test:api`

So: no strict obligation to run these manually every time, since pre-commit runs them; the obligation is not to commit code that would fail these checks.

## 3. Exhaustive compliance check before finishing

After implementation and before committing, audit every changed or created file against the relevant skills. This is not optional — it catches issues that lints and type checks miss (N+1 queries, wrong method order, missing comments, convention drift).

**What to check (API — api-layering + api-methods-entities):**

- **N+1 queries:** No queries inside loops. Use batch variants (`get_by_ids`, `sum_by_*_ids`) and load before iterating.
- **Method order:** Repositories and services follow get (list, get_by_id) → create → save → update → delete → other. Routers follow CRUD order. `__init__.py` and `__all__` lists are alphabetical.
- **Transaction rules:** Repositories never call `session.commit()`. Services commit once per use case.
- **Comments:** `#` above every function/class definition, end with period. No docstrings inside.
- **Schemas:** Request schemas inherit `RequestBase`. Response schemas inherit `BaseModel` with `model_config = {"from_attributes": True}`. Every field has `Field(description="...")`.
- **Models:** `__tablename__` set, `Field(...)` with descriptions, `utcnow` for timestamps, enums use `StrEnum` + `sa_column`.
- **Performance:** Batch variants exist for any method used in a loop. Independent external calls use `asyncio.gather()`.

**What to check (Web — web-structure + web-components-pages):**

- **Tailwind class order:** display/flex → sizing → alignment → padding → gap → bg/border → rounded → state → typography.
- **Typography tokens:** No raw `text-sm`, `text-xs`, `font-medium`. Use the type scale (`text-paragraph-*`, `text-heading-*`).
- **Component order:** consts → metadata → props → session → translations → router → state → derived → effects → handlers → return.
- **Comments:** End with period (except inline and section-header labels).
- **Translations:** Page-specific under page namespace, shared under `common`.
- **Icons:** Lucide preferred (`lucide-react`).

**What to check (both):**

- **`__init__.py` / `__all__` / import blocks** are alphabetically ordered.
- **No dead imports** from deleted files.
- **Env vars:** every new `process.env.NEXT_PUBLIC_*` read on the web or `os.getenv(...)` read on the API must have a matching entry in `.env.example` (in the right topical position) AND in `.env` (the gitignored local-dev copy). PR body must call them out under an `**Env vars:**` sub-section.
- **Docs and memory** updated per section 4 below.

## 4. Keep docs and memory current

Docs describe **how things work now**, not “what we changed” (no changelog-style “this works like this now” in READMEs).

### READMEs and DB schema

- **On every change:** If your change affects setup, structure, a specific flow or how to run/check something, update the relevant README (root, `apps/api`, `apps/web`) so it still says how things work. One source of truth; no drift.
- **DB schema changes:** If you add, remove, or modify a table, column, index, enum, or trigger, do BOTH: (1) update `apps/api/database/01_create_tables.sql` to reflect the current state — it must always rebuild the DB from zero correctly, so never add migration-style comments (“added column X”), just keep the CREATE statements current; and (2) add an Alembic migration under `apps/api/migrations/versions/` for the same change so existing databases upgrade without a rebuild. The SQL script is the canonical full schema for fresh builds (`pnpm db:init` applies it and stamps Alembic to head); migrations carry incremental changes for live DBs (`pnpm db:migrate` = `alembic upgrade head`). Generate one with `pnpm --filter api run migrate:make "message"`, review it, then run it. Keep the two in sync in the same change.

### Documentation tiers (`docs/`)

The project has three documentation tiers:

| Tier          | Path              | Committed       | Audience                        | Content                                                              |
| ------------- | ----------------- | --------------- | ------------------------------- | -------------------------------------------------------------------- |
| **Internal**  | `docs/internal/`  | No (gitignored) | Developer/agent                 | Architecture, phase specs, costs, decisions, implementation plan     |
| **Public**    | `docs/public/`    | Yes             | Anyone (non-technical friendly) | Solution overview, API reference, categories, metrics, data model    |
| **Technical** | `docs/technical/` | Yes             | Developers/agents               | Currency handling, auth flow, scheduler, env vars, providers, Docker |

**When to update each tier:**

- **`docs/internal/` (gitignored):** The agent's local memory holds the canonical list of which files in this tier to update for which event (design decisions, phase progress, architecture changes, frozen audits, etc.). Manage per those local rules.
- **`docs/public/`:** When a change affects a public doc’s accuracy — new endpoint → `api-reference.md`, new metric → `metrics.md`, new category capability → `investment-categories.md`. Keep language accessible for non-technical readers.
- **`docs/technical/`:** When implementation details change — new provider → `external-providers.md`, auth change → `auth-flow.md`, new env var → `env-vars.md`, new scheduled job → `scheduler.md`.

### Skills and memory

- **When to update skills:** Less often. Update a skill when you change a **convention** or **structure** (e.g. new layer, new place for components, new comment style). If you only added a feature following existing conventions, you usually don’t need to edit a skill.
- **Memory:** After finishing significant work, update the agent's local memory per the agent's own memory rules. Each agent (Claude, Codex, others) has its own memory system at its own path. Do not write to another agent's memory directory. Skip memory updates for trivial fixes.

## 5. What NOT to commit

- **Never stage `.claude/plans/`** — agent plans are ephemeral working docs, gitignored.
- **Never stage `docs/internal/`** — internal docs (architecture, phase specs, costs, decisions) are gitignored.
- **Never stage temporary markdown files** (e.g. scratch notes, plan drafts, ad-hoc `.md` files) unless the user explicitly asks to commit a specific file by name. When staging, always list files individually — never `git add .` or `git add -A` — so stray files are not accidentally included.

## 6. Skill mirrors (`.claude/skills/` ↔ `.agents/skills/`)

Skills under `.claude/skills/` and `.agents/skills/` are mirrored — Claude reads from the first tree, Codex from the second. The mirrors are kept **byte-equal**. There is no intentional drift; if you spot a difference between the two trees that isn't a transient mid-edit state, treat it as a bug.

**Rules when editing a mirrored skill:**

- Make the change in BOTH mirrors in the same edit pass.
- **Never `cp .claude/skills/<name>/SKILL.md .agents/skills/<name>/SKILL.md`** (or the reverse) — even though byte-equality is the goal, the safer path is targeted edits + a `diff .claude/skills/<name>/SKILL.md .agents/skills/<name>/SKILL.md` check afterward (catches per-agent specifics that snuck in mid-edit).
- **Don't introduce agent-specific cross-references that wouldn't resolve on the other side.** Examples to avoid: Claude `[[memory-link]]` syntax pointing to Claude-only memory files; by-name references to gitignored files only one agent has. When you want to cite a per-agent convention, write the rule's content inline in both mirrors instead.
- **Use agent-agnostic language for things that vary per agent.** "Manage per the agent's local memory rules" works for both Claude and Codex (each interprets it in its own environment). "Update Claude memory files" or "Codex doesn't have memory" would force drift.
- When in doubt about whether content should mirror, default to **mirror it**. Drift creates a maintenance tax that has rarely been worth it in this repo.

## 7. Other habits

- **Scope:** Know which app you’re in (`apps/api` vs `apps/web`). Use the right tooling (e.g. `uv` in API, `pnpm --filter web` for web).
- **After big refactors:** Run `pnpm check:api` and `pnpm check:web` once to catch import/model/type errors before the user hits pre-commit.
- **Hooks:** Don’t remove or weaken pre-commit checks without a clear reason; they’re there so CI and local stay aligned.
- **Paths and config:** API uses `app.*` and `apps/api` as cwd; web uses `@/` aliases and `config/routes.ts`. Follow the structure and skills so new code lands in the right place.
- **Empty folders:** When adding the first real file to a folder that only had a `.gitkeep`, remove the `.gitkeep` so the folder is no longer “empty” and the new file is the only content.
