# Renly API

FastAPI backend for Renly.

## Install

```bash
cd apps/api && uv sync
```

(Or with venv: `pip install -r requirements.txt`.)

## Run

From repo root: `pnpm dev:api`  
From here: `uv run uvicorn app.main:app --reload --port 8000`

Docs (Swagger): http://localhost:8000/docs

**Local DB:** From repo root, `pnpm db:init` starts Postgres and applies the schema.

## Check (no server)

From repo root: `pnpm check:api` — same as pre-commit/CI; catches import and model errors. (Runs `uv run python -c "from app.main import app"` in `apps/api`.)

## Migrations

Schema is managed two ways that stay in sync:

- `apps/api/database/01_create_tables.sql` — the canonical full schema. `pnpm db:init` builds a fresh DB from it and stamps Alembic to head.
- `apps/api/database/00_roles.sql` — the roles (`renly_admin`, `renly_app`, `renly_policy_definer`), their memberships and `renly_admin`'s default privileges: everything a NOSUPERUSER owner cannot do for itself. Run as a superuser before `01_create_tables.sql` (`pnpm db:init` does); idempotent, and the prerequisite a migration names when it needs a role that does not exist yet.
- Alembic migrations (`apps/api/migrations/versions/`) — incremental changes for existing databases. `pnpm db:migrate` (`alembic upgrade head`) brings a live DB up to date.

When you change the schema, update **both**: edit `01_create_tables.sql` and add a migration — `pnpm --filter api run migrate:make "describe the change"` (autogenerates against the models), review the generated file under `migrations/versions/`, then `pnpm db:migrate`.

Migrations run as `renly_admin`; `migrations/env.py` hands everything they create to the table owner afterwards, and `renly_admin`'s default privileges give `renly_app` its DML grants on new tables and sequences. One thing it cannot do for you: a **new `SECURITY DEFINER` function** (or a helper dropped and re-created rather than `CREATE OR REPLACE`d, which keeps its owner) ends up owned by the table owner, which is subject to the FORCEd policies. Hand it to `renly_policy_definer` in both files — the grant-CREATE / `ALTER FUNCTION … OWNER TO` / revoke-CREATE block after `app_is_group_member()` in `01_create_tables.sql`, and `0030_policy_definer.py` for the migration shape — and grant that role `SELECT` on exactly the tables the body reads. `tests/integration/test_rls_force_role_model.py` fails until you do.

## Structure

Request flow: **router → service → repository → DB**. Routers are HTTP-only; services hold business logic; repositories do data access. Schemas for request/response; `deps/` for FastAPI dependencies.

## Test

From repo root: `pnpm test:api`
From here: `uv run pytest tests/ -v`

`tests/integration/` needs a real Postgres and is **skipped by default** — each file gates on its own
env var, so a green `pnpm test:api` says nothing about it. Point them at a throwaway DB with the schema
applied:

```bash
# RLS isolation — needs BOTH the restricted request role and the BYPASSRLS admin role
RLS_TEST_DATABASE_URL=postgresql+asyncpg://renly_app:renly_app@localhost:5432/<db> \
RLS_TEST_ADMIN_DATABASE_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:5432/<db> \
  uv run pytest tests/integration/test_rls_isolation.py

# Account-ledger drift, group lifecycle and the query suites — the BYPASSRLS admin role only
LEDGER_TEST_DATABASE_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:5432/<db> \
  uv run pytest tests/integration/test_account_ledger_drift.py
GROUPS_TEST_DATABASE_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:5432/<db> \
  uv run pytest tests/integration/test_group_lifecycle.py

# All of them at once
RLS_TEST_DATABASE_URL=... RLS_TEST_ADMIN_DATABASE_URL=... \
LEDGER_TEST_DATABASE_URL=... GROUPS_TEST_DATABASE_URL=... \
  uv run pytest tests/integration
```

The URLs must carry the `postgresql+asyncpg://` prefix. The two login roles' local passwords are set by `database/00_roles.sql` (`renly_app` / `renly_admin`) and are **not** the owner's. Not the owner for any of them: under FORCE a non-superuser owner reads nothing, and the local superuser owner reads everything, so neither exercises what the suites assert.

Against a superuser-owned local database the RLS suites cannot see a defect that only a NOSUPERUSER owner exposes. To run them production-shaped, create the database `OWNER` a throwaway `NOSUPERUSER NOBYPASSRLS` role, run `00_roles.sql` against it as the superuser, and apply `01_create_tables.sql` as that role.

## Env

`.env` with: `DATABASE_URL`, `DATABASE_ADMIN_URL`, `JWT_SECRET` (match Next.js `NEXTAUTH_SECRET`), `JWT_ALGORITHM=HS256`, `JWT_EXPIRE_MINUTES=30` (short access token; the web silently refreshes it — AUTH-7), `REFRESH_TOKEN_REMEMBER_DAYS=30` / `REFRESH_TOKEN_DEFAULT_HOURS=12` (refresh-token lifetimes for remembered vs ordinary logins), `ENVIRONMENT` (`development`/`production` — `production` disables docs and debug), `CORS_ORIGINS` (comma-separated allowed origins), `TRUSTED_PROXY_COUNT` (reverse-proxy hop count for client-IP rate limiting; `0` when reached directly), `WEB_BASE_URL` (web app URL used to build account-email links), `SIGNUP_MODE` (`invite` default / `open` — the invite-only access gate), and the transactional-email settings `EMAIL_PROVIDER` (`console`/`resend`), `EMAIL_API_KEY`, `EMAIL_FROM` (SHELL-3). Web push adds `VAPID_PRIVATE_KEY` (empty = this deployment sends no push, and the app says so) and the optional `VAPID_SUBJECT`; there is no public-key setting because the browser's `applicationServerKey` is derived from the private one, so the pair cannot be mismatched. Copy from `.env.example`. External API URLs (DolarApi, Frankfurter, CoinGecko, Comafi) are constants in the service layer.

**Two DB URLs, three login roles (Row-Level Security, SEC-15):** request connections use `DATABASE_URL` — a **restricted** role (`renly_app`: `NOBYPASSRLS`, not the table owner) so per-user RLS policies apply. Context-less work (scheduler, migrations, login/register/API-key verification) uses `DATABASE_ADMIN_URL` — **`renly_admin`**, which has `BYPASSRLS` and is a member of the owner. Neither URL names the owner (`renly`): every policied table is `FORCE`d, so in production (a NOSUPERUSER owner) it reads nothing. `pnpm db:init` provisions the roles (`00_roles.sql`) and the policies (`01_create_tables.sql`). `DATABASE_ADMIN_URL` falls back to `DATABASE_URL` when unset, which leaves context-less work reading nothing — login included — so set it everywhere. See `docs/technical/deployment.md` → Roles.

**First admin (invite-only signup):** with `SIGNUP_MODE=invite` and no admin yet, nobody can self-register — so the first admin is set directly in the DB. Run once **as `renly_admin`** (the `DATABASE_ADMIN_URL` role), then invite everyone else from `/admin`:

```sql
UPDATE users SET is_admin = true WHERE email = 'you@example.com';
```

Check it reports `UPDATE 1`. Run as a NOSUPERUSER owner (or as `renly_app`), the FORCEd policy matches no row and it reports `UPDATE 0` and succeeds — the flag is silently not set.

Flag more rows to add more admins (multi-admin, not a role system). See `docs/technical/auth-flow.md` → Invite-only access gate.
