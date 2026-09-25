# Deployment runbook

Renly ships as **two Docker images** behind an **env contract** — that's the entire deploy
surface, so it runs on any container host. The platform is chosen at deploy time; nothing here is
activated. This runbook describes what a host needs to build, configure, run, and migrate.

> **Status:** documented, not activated. No production credentials live in the repo and no deploy
> is wired to run automatically. Provisioning a host is a deliberate go-live step.

---

## The deployable unit — two images

Both build from the repo root (the build context must be the root so the API image can copy
`apps/api/` and the web image can resolve the pnpm workspace):

```bash
# API (FastAPI) — listens on $PORT
docker build -f docker/api.Dockerfile -t renly-api .

# Web (Next.js) — NEXT_PUBLIC_* values are inlined at build time, so both must be set at image
# build (a runtime-only value has no effect). The Sentry DSN is optional (empty = Sentry off).
docker build -f docker/web.Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  --build-arg NEXT_PUBLIC_SENTRY_DSN=https://examplekey@o0.ingest.sentry.io/0 \
  -t renly-web .
```

Run commands (both honor `$PORT`):

```bash
# API
docker run -e PORT=8000 -e DATABASE_URL=... -e DATABASE_ADMIN_URL=... -e JWT_SECRET=... renly-api
#   image CMD: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}   (binds $PORT, defaults to 8000)

# Web
docker run -e PORT=3000 renly-web
#   image CMD: next start   (serves the prebuilt .next on $PORT)
```

Health check (API): `GET /health` → `{"status":"ok"}` (rate-limit exempt).

---

## Env contract

Set these in the host's secret store (not in the repo). Full reference: [`env-vars.md`](./env-vars.md).

**API:**

| Variable              | Notes                                                                                                                                              |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`        | The **restricted `renly_app` role** (NOBYPASSRLS, non-owner) — request connections are subject to RLS.                                             |
| `DATABASE_ADMIN_URL`  | The **`renly_admin` role** (BYPASSRLS, not a superuser, a member of the owner) — migrations, the scheduler, and pre-auth lookups. Never the owner. |
| `JWT_SECRET`          | Must equal the web app's `NEXTAUTH_SECRET`; min 32 chars.                                                                                          |
| `ENVIRONMENT`         | `production` disables `/docs` and tracebacks.                                                                                                      |
| `CORS_ORIGINS`        | Comma-separated allowed origins (the production web URL).                                                                                          |
| `TRUSTED_PROXY_COUNT` | Hop count of proxies in front of the app (for client-IP rate limiting).                                                                            |
| `SENTRY_DSN`          | Optional; enables API error tracking.                                                                                                              |

**Web:**

| Variable                                              | Notes                                                                                                                            |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `NEXTAUTH_SECRET`                                     | Must equal the API's `JWT_SECRET`.                                                                                               |
| `NEXTAUTH_URL`                                        | The production web URL.                                                                                                          |
| `NEXT_PUBLIC_API_URL`                                 | The API URL — **build arg** (inlined), so set it at image build, not just runtime.                                               |
| `NEXT_PUBLIC_SENTRY_DSN`                              | Optional; enables web error tracking. **Build arg** (inlined) like `NEXT_PUBLIC_API_URL` — set at image build, not just runtime. |
| `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` | Optional, build-only — set to upload source maps; without the token the build neither uploads nor needs them.                    |

---

## Roles

Three login roles and one helper role, and which one a connection string names is the entire
isolation boundary:

| Role                   | Attributes                                                                                | Used by                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| `renly`                | owner, **NOSUPERUSER**, **NOBYPASSRLS**                                                   | nothing at runtime — it exists to own the tables                   |
| `renly_admin`          | **BYPASSRLS**, member of `renly`                                                          | `DATABASE_ADMIN_URL`, migrations, `pnpm db:backup`, `pnpm db:fork` |
| `renly_app`            | DML grants only, **NOBYPASSRLS**                                                          | `DATABASE_URL` — every request connection                          |
| `renly_policy_definer` | **NOLOGIN**, **BYPASSRLS**, `SELECT` on `pots`, `group_members`, `pot_member_permissions` | nothing connects — it owns the three `SECURITY DEFINER` helpers    |

Every policied table carries `FORCE ROW LEVEL SECURITY`, so **owning a table is no longer an
exemption from its policies**. A connection pointed at `renly` reads nothing rather than everything,
which is the point: the previous two-role model made "wrong URL" and "no isolation" the same
mistake, and both local dev and this document used to make it.

**The owner must not be a superuser.** A superuser bypasses RLS whatever the table says, so `FORCE`
is completely inert against one — which makes this the part of the model with actual security value
rather than a formality. Provision `renly` with `NOSUPERUSER NOBYPASSRLS` and grant it only ownership
of the database.

**Why the helper role exists.** The policies on `groups`, `group_members`, `pots` and the pot-scoped
tables call `SECURITY DEFINER` helpers, which run as their owner. Were that the table owner, it would
be subject to the policy that called it — `group_members`' policy calls `app_is_group_member()`,
which reads `group_members` — and every group and pot read would recurse until `stack depth limit
exceeded`. `renly_policy_definer` bypasses RLS without owning any table, and can read only what the
helpers read.

### Provisioning (superuser, once per database)

The owner cannot create roles or grant memberships, so a **superuser** (the platform's admin role)
does this before anything else:

```sql
-- 1. The owner, and the database it owns.
CREATE ROLE renly LOGIN PASSWORD '<secret>' NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
CREATE DATABASE renly OWNER renly;
```

```bash
# 2. Everything else the owner cannot do for itself, connected to that database. Idempotent.
psql -v ON_ERROR_STOP=1 -U <superuser> -d renly -f apps/api/database/00_roles.sql
# then set real passwords on the two login roles:
psql -U <superuser> -d renly -c "ALTER ROLE renly_admin PASSWORD '<secret>'" -c "ALTER ROLE renly_app PASSWORD '<secret>'"
```

`00_roles.sql` creates `renly_admin`, `renly_app` and `renly_policy_definer`; makes `renly_admin` a
member of the database owner and the owner a member of `renly_policy_definer` (which is how the owner,
and through it `renly_admin`, may hand the helpers to it); and declares `renly_admin`'s default
privileges, so tables and sequences a migration creates reach `renly_app` with their grants.

Then build the schema **as the owner**, so the owner owns what it creates:

```bash
psql -v ON_ERROR_STOP=1 -U renly -d renly -f apps/api/database/01_create_tables.sql
cd apps/api && DATABASE_ADMIN_URL=<renly_admin url> uv run alembic stamp head
```

`01_create_tables.sql` creates no role and grants no membership — a NOSUPERUSER owner would be refused
both, and the refusal of a membership grant is only a `NOTICE`, which is exactly the kind of failure
nobody reads. Instead it checks, before creating anything, that the three roles exist and that the
role applying it may act as `renly_policy_definer`, and stops with a hint naming `00_roles.sql` if not.
Both files set `ON_ERROR_STOP` themselves (the `-v ON_ERROR_STOP=1` above says the same thing twice on
purpose), because psql's default is to report a failed statement and carry on: a schema run that way
exits 0 half-built, and the `alembic stamp head` after it would mark that as current.

## Migrations

Migrations run as **`renly_admin`**, which is what `DATABASE_ADMIN_URL` names:

```bash
# From apps/api. env.py reads DATABASE_ADMIN_URL; do not point DATABASE_URL at a privileged role.
uv run alembic upgrade head        # == pnpm db:migrate
```

Two reasons it must be that role and not the owner. It has to ALTER owner-owned objects, which only a
member of the owner may do; and several migrations backfill across every user's rows. Under `FORCE` a
backfill run without `BYPASSRLS` matches nothing, reports `UPDATE 0` and **exits 0** — a data
migration that silently does nothing. `migrations/env.py` guards that by setting `row_security = off`,
which a role without `BYPASSRLS` cannot satisfy: the first statement touching a policied table raises
`query would be affected by row-level security policy` instead. Wrong role, immediate failure.

`env.py` also runs `REASSIGN OWNED BY renly_admin TO <owner of users>` after each upgrade, so objects
a migration creates end up owned by the table owner rather than by the role that ran it — a table
owned by a `BYPASSRLS` role is a table `FORCE` can never apply to.

**Migrations cannot provision roles.** `renly_admin` has no `CREATEROLE`, and it cannot grant itself
membership in anything, so a migration that needs a new role checks for it and stops with a `HINT`
naming `00_roles.sql` rather than trying. (`0029_rls_force` does contain a guarded `CREATE ROLE
renly_admin` and a `GRANT <current user> TO renly_admin`. Run as `renly_admin`, as `pnpm db:migrate`
does, the first is skipped because the role exists and the second tries to grant `renly_admin` to
itself, which is refused (`permission denied to grant role`) and swallowed into a `NOTICE`. Both are
no-ops; `00_roles.sql` is what provides them.) `0030` is the first migration that depends on
`00_roles.sql` having run: it hands the three helpers to `renly_policy_definer`.

A fresh database is built per [Provisioning](#provisioning-superuser-once-per-database) and stamped to
head; existing databases upgrade via the migration chain. The model is plain Postgres roles and
`FORCE`, so it ports to any host.

---

## Database & backups

The database is any managed PostgreSQL. Provision it per [Provisioning](#provisioning-superuser-once-per-database)
— a **non-superuser** owner, then `00_roles.sql` as the platform's superuser, then the schema as the
owner — and give each connection string the role from the table above. For backups and the rehearsed restore procedure, see
[`backups.md`](./backups.md). If the chosen host offers its own automated backups, enable them at
go-live as an additional layer.

---

## CI

`ci.api.yml` and `ci.web.yml` run lint / type-check / build / tests on every PR. They are not
deploy pipelines — wiring a deploy step is done against the chosen host at go-live.
