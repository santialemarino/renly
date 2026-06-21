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

# Web (Next.js) — NEXT_PUBLIC_API_URL is inlined at build time, so it must be the real API URL
docker build -f docker/web.Dockerfile --build-arg NEXT_PUBLIC_API_URL=https://api.example.com -t renly-web .
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

| Variable                                              | Notes                                                                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `NEXTAUTH_SECRET`                                     | Must equal the API's `JWT_SECRET`.                                                                            |
| `NEXTAUTH_URL`                                        | The production web URL.                                                                                       |
| `NEXT_PUBLIC_API_URL`                                 | The API URL — **build arg** (inlined), so set it at image build, not just runtime.                            |
| `NEXT_PUBLIC_SENTRY_DSN`                              | Optional; enables web error tracking.                                                                         |
| `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` | Optional, build-only — set to upload source maps; without the token the build neither uploads nor needs them. |

---

## Migrations

Migrations run with the **owner** role, not the restricted request role:

```bash
# From apps/api, with DATABASE_URL pointed at the owner role (or export DATABASE_ADMIN_URL as DATABASE_URL):
uv run alembic upgrade head        # == pnpm db:migrate
```

A fresh database is built from `apps/api/database/01_create_tables.sql` (which also provisions the
`renly_app` role + RLS policies) and stamped to head; existing databases upgrade via the migration
chain. The RLS two-role model is plain Postgres, so it ports to any host.

---

## Database & backups

The database is any managed PostgreSQL. Provision it, apply the schema/migrations, and create the
`renly_app` role per `01_create_tables.sql`. For backups and the rehearsed restore procedure, see
[`backups.md`](./backups.md). If the chosen host offers its own automated backups, enable them at
go-live as an additional layer.

---

## CI

`ci.api.yml` and `ci.web.yml` run lint / type-check / build / tests on every PR. They are not
deploy pipelines — wiring a deploy step is done against the chosen host at go-live.
