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

| Variable              | Notes                                                                                                                                            |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`        | The **restricted `renly_app` role** (NOBYPASSRLS, non-owner) — request connections are subject to RLS.                                           |
| `DATABASE_ADMIN_URL`  | The **table-owner role** — used for migrations, the scheduler, and pre-auth lookups (bypasses RLS). Must be a distinct owner role in production. |
| `JWT_SECRET`          | Must equal the web app's `NEXTAUTH_SECRET`; min 32 chars.                                                                                        |
| `ENVIRONMENT`         | `production` disables `/docs` and tracebacks.                                                                                                    |
| `CORS_ORIGINS`        | Comma-separated allowed origins (the production web URL).                                                                                        |
| `TRUSTED_PROXY_COUNT` | Hop count of proxies in front of the app (for client-IP rate limiting).                                                                          |
| `SENTRY_DSN`          | Optional; enables API error tracking.                                                                                                            |

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

Three roles, and which one a connection string names is the entire isolation boundary:

| Role          | Attributes                              | Used by                                                            |
| ------------- | --------------------------------------- | ------------------------------------------------------------------ |
| `renly`       | owner, **NOSUPERUSER**, **NOBYPASSRLS** | nothing at runtime — it exists to own the tables                   |
| `renly_admin` | **BYPASSRLS**, member of `renly`        | `DATABASE_ADMIN_URL`, migrations, `pnpm db:backup`, `pnpm db:fork` |
| `renly_app`   | DML grants only, **NOBYPASSRLS**        | `DATABASE_URL` — every request connection                          |

Every policied table carries `FORCE ROW LEVEL SECURITY`, so **owning a table is no longer an
exemption from its policies**. A connection pointed at `renly` reads nothing rather than everything,
which is the point: the previous two-role model made "wrong URL" and "no isolation" the same
mistake, and both local dev and this document used to make it.

**The owner must not be a superuser.** A superuser bypasses RLS whatever the table says, so `FORCE`
is completely inert against one — which makes this the part of the model with actual security value
rather than a formality. Provision `renly` with `NOSUPERUSER NOBYPASSRLS` and grant it only ownership
of the database.

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

`env.py` also runs `REASSIGN OWNED BY renly_admin TO <owner>` after each upgrade, so objects a
migration creates end up owned by `renly` rather than by the role that ran it — a table owned by a
`BYPASSRLS` role is a table `FORCE` can never apply to.

A fresh database is built from `apps/api/database/01_create_tables.sql` (which provisions both
non-owner roles, the policies and `FORCE`) and stamped to head; existing databases upgrade via the
migration chain. The model is plain Postgres roles and `FORCE`, so it ports to any host.

---

## Database & backups

The database is any managed PostgreSQL. Provision it with a **non-superuser** owner, apply the
schema/migrations (which create `renly_admin` and `renly_app` per `01_create_tables.sql`), and give
each connection string the role from the table above. For backups and the rehearsed restore procedure, see
[`backups.md`](./backups.md). If the chosen host offers its own automated backups, enable them at
go-live as an additional layer.

---

## CI

`ci.api.yml` and `ci.web.yml` run lint / type-check / build / tests on every PR. They are not
deploy pipelines — wiring a deploy step is done against the chosen host at go-live.
