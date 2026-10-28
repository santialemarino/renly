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
# API (FastAPI) — listens on $PORT. Installs exactly what apps/api/uv.lock pins (`uv sync --locked`),
# so the build fails if the lockfile is out of date with pyproject.toml.
docker build -f docker/api.Dockerfile -t renly-api .

# Web (Next.js) — NEXT_PUBLIC_* values are inlined at build time, so both must be set at image
# build (a runtime-only value has no effect). The Sentry DSN is optional (empty = Sentry off).
# The last three lines upload source maps to Sentry and are optional too: drop them and the build
# uploads nothing. The token is read from the builder's SENTRY_AUTH_TOKEN env var as a BuildKit
# secret, so it reaches `next build` and nothing else — no image layer, no `docker history`.
SENTRY_AUTH_TOKEN=<sentry auth token> docker build -f docker/web.Dockerfile \
  --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  --build-arg NEXT_PUBLIC_SENTRY_DSN=https://examplekey@o0.ingest.sentry.io/0 \
  --build-arg SENTRY_ORG=<org slug> \
  --build-arg SENTRY_PROJECT=<project slug> \
  --secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN \
  -t renly-web .
```

Run commands (both honor `$PORT`):

```bash
# API
docker run -e PORT=8000 -e ENVIRONMENT=production -e DATABASE_URL=... -e DATABASE_ADMIN_URL=... -e JWT_SECRET=... renly-api
#   image CMD: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}   (binds $PORT, defaults to 8000)

# Web
docker run -e PORT=3000 renly-web
#   image CMD: next start   (serves the prebuilt .next on $PORT)
```

Health check (API): `GET /health` → `{"status":"ok"}` (rate-limit exempt).

**In production the API needs the database at boot.** Startup reads the role model through
`DATABASE_URL` ([Roles](#roles)), so an unreachable database makes the process exit instead of
starting and connecting later, as development still does. Give the API container a restart policy
that retries (or start it after the database is healthy).

---

## Env contract

Set these in the host's secret store (not in the repo). Full reference: [`env-vars.md`](./env-vars.md).

**API:**

| Variable              | Notes                                                                                                                                                                                                                                                                           |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DATABASE_URL`        | The **restricted `renly_app` role** (NOBYPASSRLS, non-owner) — request connections are subject to RLS. In production the API refuses to start when it, or the tables' owner, can bypass RLS — see [Roles](#roles).                                                              |
| `DATABASE_ADMIN_URL`  | The **`renly_admin` role** (BYPASSRLS, not a superuser, a member of the owner) — migrations, the scheduler, and pre-auth lookups. Never the owner.                                                                                                                              |
| `JWT_SECRET`          | Must equal the web app's `NEXTAUTH_SECRET`; min 32 chars.                                                                                                                                                                                                                       |
| `ENVIRONMENT`         | `production` disables `/docs` and tracebacks. **Required** — the API refuses to start without it.                                                                                                                                                                               |
| `CORS_ORIGINS`        | Comma-separated allowed origins (the production web URL).                                                                                                                                                                                                                       |
| `TRUSTED_PROXY_COUNT` | Hop count of proxies in front of the app (for client-IP rate limiting).                                                                                                                                                                                                         |
| `INTERNAL_API_SECRET` | Must equal the web app's `INTERNAL_API_SECRET`; min 32 chars. Lets the web server's own calls be rate-limited per visitor — see [Client IPs and rate limits](#client-ips-and-rate-limits).                                                                                      |
| `WEB_BASE_URL`        | The production web URL (no trailing slash). Every account-email link (verification, password reset, invites) is built from it.                                                                                                                                                  |
| `SIGNUP_MODE`         | `invite` (default) — registering needs an admin invite — or `open`.                                                                                                                                                                                                             |
| `EMAIL_PROVIDER`      | `resend` in production. The default, `console`, only logs each message, so nobody receives a verification link and nobody can finish signing up.                                                                                                                                |
| `EMAIL_API_KEY`       | The Resend API key. Required when `EMAIL_PROVIDER=resend` — the API refuses to start without it.                                                                                                                                                                                |
| `EMAIL_FROM`          | The sender, e.g. `Renly <noreply@yourdomain.com>` — a sender verified with Resend. The default is Resend's shared `onboarding@resend.dev`, which delivers only to the Resend account owner, so with `resend` in production the API refuses to start on any `resend.dev` sender. |
| `VAPID_PRIVATE_KEY`   | Optional; enables web push (empty = this deployment sends none). `VAPID_SUBJECT` optionally names its contact.                                                                                                                                                                  |
| `SENTRY_DSN`          | Optional; enables API error tracking.                                                                                                                                                                                                                                           |

With `SENTRY_DSN` set, add a Sentry alert rule at deploy on events whose message starts with `SCHEDULED JOB FAILED` (the recommended default): a failed background job is reported there and in the logs, nowhere else ([scheduler](scheduler.md#error-handling)).

**Web:**

| Variable                                              | Notes                                                                                                                                                                                                                                                                                                                                                                                                       |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `NEXTAUTH_SECRET`                                     | Must equal the API's `JWT_SECRET`.                                                                                                                                                                                                                                                                                                                                                                          |
| `NEXTAUTH_URL`                                        | The production web URL.                                                                                                                                                                                                                                                                                                                                                                                     |
| `INTERNAL_API_SECRET`                                 | Must equal the API's `INTERNAL_API_SECRET`; min 32 chars (warned at startup). Runtime, server-only — never a build arg, never `NEXT_PUBLIC_`.                                                                                                                                                                                                                                                               |
| `WEB_TRUSTED_PROXY_COUNT`                             | Hop count of proxies in front of the web server — see [Client IPs and rate limits](#client-ips-and-rate-limits).                                                                                                                                                                                                                                                                                            |
| `NEXT_PUBLIC_API_URL`                                 | The API URL — **build arg** (inlined), so set it at image build, not just runtime.                                                                                                                                                                                                                                                                                                                          |
| `NEXT_PUBLIC_SENTRY_DSN`                              | Optional; enables web error tracking. **Build arg** (inlined) like `NEXT_PUBLIC_API_URL` — set at image build, not just runtime.                                                                                                                                                                                                                                                                            |
| `SENTRY_AUTH_TOKEN` / `SENTRY_ORG` / `SENTRY_PROJECT` | Optional, build only: read by `next build` to upload source maps, so Sentry shows readable stack traces. The token is a BuildKit **secret** (`--secret id=sentry_auth_token,env=SENTRY_AUTH_TOKEN`), org and project are **build args** — see [the build command](#the-deployable-unit--two-images). Without the token the build neither uploads nor needs them, and Sentry receives minified stack traces. |

---

## Client IPs and rate limits

The API rate-limits by user id when a request carries a valid bearer token, and by client IP
otherwise (login, registration, the password and email flows, and token refresh all arrive without
one). Two paths reach it:

- **Browser → API** — the signup, forgot-password, reset and verify forms call the API directly. The
  API reads the client from `X-Forwarded-For` under its own `TRUSTED_PROXY_COUNT`.
- **Browser → web server → API** — sign-in (Auth.js), token refresh and the signup-context read are
  made BY the web server, so the API's peer is the web server. Without forwarding, every visitor's
  login shares one bucket (5 a minute for the whole site). The web server reads the visitor from its
  own `X-Forwarded-For` under `WEB_TRUSTED_PROXY_COUNT` and sends it in `X-Renly-Client-IP` with
  `INTERNAL_API_SECRET` in `X-Renly-Internal-Secret`; the API honours that header only when the
  secret matches.

To set it up, generate one secret (`openssl rand -hex 32`, at least 32 characters), put the SAME
value in `INTERNAL_API_SECRET` on both apps, and set each hop count to the number of proxies in front
of THAT app. Both counts read `X-Forwarded-For` from the right, so a client can only add entries the
count skips; a count higher than the real number of proxies lets a client choose its own key. The web
server warns at startup when its `INTERNAL_API_SECRET` is set but shorter than 32 characters: the API
refuses to start with one that short, so the two can never match and every server-side call falls back
to the web server's own bucket.

**Close every direct route to the origin.** The counts assume every request passes through all the
trusted proxies. A request that reaches an app another way — the hosting platform's default
hostname, the origin's IP, a route around the CDN — arrives with a shorter
`X-Forwarded-For` chain than the count expects, and when the chain is shorter than the hop count both
apps fall back to its LEFTMOST entry, which the client wrote. That lets a client pick its own
rate-limit key, on the web side (and so on the forwarded login and refresh calls) as well as the API
side. Disable or firewall those routes so the proxies are the only way in.

| Topology                                                             | API `TRUSTED_PROXY_COUNT` | Web `WEB_TRUSTED_PROXY_COUNT` |
| -------------------------------------------------------------------- | ------------------------- | ----------------------------- |
| Both apps reached directly (local dev)                               | `0`                       | `0` — nothing is forwarded    |
| One load balancer / platform router in front of each app             | `1`                       | `1`                           |
| A CDN in front of the platform router, for each app                  | `2`                       | `2`                           |
| Web behind a router, API reached directly by the browser and the web | `0`                       | `1`                           |

The web server's own call to the API does not pass through the web's proxies; when it goes back out
through the API's public router, that router adds the web server's address, which the forwarded header
supersedes. With `WEB_TRUSTED_PROXY_COUNT=0` the web forwards nothing: Next fills `X-Forwarded-For` only
when a request arrives without one, so a directly reached web server cannot tell its peer from a value
the client sent. With `INTERNAL_API_SECRET` unset on either side, nothing changes: the server-side calls
are limited by the web server's address, as before. The two forwarding headers are scrubbed from the
API's Sentry events.

---

## Roles

Three login roles and one helper role, and which one a connection string names is the entire
isolation boundary:

| Role                   | Attributes                                                                                                                              | Used by                                                                                                       |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `renly`                | owner, **NOSUPERUSER**, **NOBYPASSRLS**                                                                                                 | nothing at runtime — it exists to own the tables                                                              |
| `renly_admin`          | **BYPASSRLS**, member of `renly`                                                                                                        | `DATABASE_ADMIN_URL`, migrations, `pnpm db:backup`, `pnpm db:fork`                                            |
| `renly_app`            | DML grants only, **NOBYPASSRLS**                                                                                                        | `DATABASE_URL` — every request connection                                                                     |
| `renly_policy_definer` | **NOLOGIN**, **BYPASSRLS**, `SELECT` on `pots`, `group_members`, `pot_member_permissions` and on `accounts` (`id`, `user_id`, `pot_id`) | nothing connects — it owns the four `SECURITY DEFINER` functions (three policy helpers, one trigger function) |

Every policied table carries `FORCE ROW LEVEL SECURITY`, so **owning a table is no longer an
exemption from its policies**. A connection pointed at `renly` reads nothing rather than everything,
which is the point: the previous two-role model made "wrong URL" and "no isolation" the same
mistake, and both local dev and this document used to make it.

**The owner must not be a superuser.** A superuser bypasses RLS whatever the table says, so `FORCE`
is completely inert against one — which makes this the part of the model with actual security value
rather than a formality. Provision `renly` with `NOSUPERUSER NOBYPASSRLS` and grant it only ownership
of the database.

**Production refuses to start on a model that does not isolate.** With `ENVIRONMENT=production` the
API reads the catalogue once at startup, through `DATABASE_URL`, and exits naming what is wrong when
the request role is `SUPERUSER` or `BYPASSRLS` or a member of a role that is (it could `SET ROLE` into
it), when it owns a policied table or is a member of its owner (it could switch the table's RLS off),
when the owner of any policied table is `SUPERUSER` or `BYPASSRLS` (a superuser owner is what a host
that hands over its own admin role produces), when a policied table lacks `FORCE ROW LEVEL SECURITY`
or has RLS disabled, or when no table has RLS at all. The policied tables are derived from the
catalogue (RLS enabled or a policy defined), not listed. `renly_app` as `00_roles.sql` provisions it
owns nothing and is a member of no role, so it passes. Development skips the check, because a local
owner is usually the superuser that created the cluster.

**Why the helper role exists.** The policies on `groups`, `group_members`, `pots` and the pot-scoped
tables call `SECURITY DEFINER` helpers, which run as their owner. Were that the table owner, it would
be subject to the policy that called it — `group_members`' policy calls `app_is_group_member()`,
which reads `group_members` — and every group and pot read would recurse until `stack depth limit
exceeded`. `renly_policy_definer` bypasses RLS without owning any table, and can read only what the
helpers read. It also owns the trigger function that holds every account reconciliation to its
account's scope, which reads three columns of `accounts` and is granted only those.

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

### Connection budget

Each API process opens at most **30 connections**: three pools, each `pool_size` + `max_overflow`
(deliberate constants in `apps/api/app/db.py`, not env):

| Pool    | Role          | Max | Serves                                                                             |
| ------- | ------------- | --- | ---------------------------------------------------------------------------------- |
| request | `renly_app`   | 20  | every authenticated request                                                        |
| admin   | `renly_admin` | 5   | the scheduler, notification dispatch, the admin surface, cross-user bootstrap work |
| auth    | `renly_admin` | 5   | login, register, refresh, verification, password reset, API-key verification       |

Size the database for `30 × API processes` plus migrations, backups and a superuser session. A
small managed Postgres (often ~22–25 usable connections) does not fit even one process at peak —
pick a plan above that, or put a pooler (PgBouncer in transaction mode) in front.

---

## CI

`ci.api.yml` and `ci.web.yml` run lint / type-check / build / tests on PRs that touch their app or their own
workflow file (`ci.web.yml` also on any file Prettier formats, since it checks the whole tree), on the
versions the images run (Python 3.14, the API image's base, with `uv sync --locked`; Node from `.nvmrc`). `ci.web.yml`
also checks Prettier formatting over the whole tree and lints and type-checks `packages/ui`. `ci.api.yml`
also replays the migration chain from its baseline — online, and as the script `alembic upgrade --sql`
writes — and fails when either database's schema differs from the one `01_create_tables.sql` builds.
`ci.web-e2e.yml` runs the Playwright suite against compose's Postgres (built by `pnpm db:init`), the
API and a production web build: on a PR that touches its floor paths or carries the `run-e2e` label,
every night on `main`, and on demand. Its `e2e-required` job is the one to mark as a required check.
The `e2e-testing` skill describes the job. None of them is a deploy pipeline — wiring a deploy step is
done against the chosen host at go-live.
