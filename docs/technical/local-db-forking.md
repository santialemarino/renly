# Local Database Setup Guide

**First-time DB (docker-compose):** From repo root, run `pnpm db:init` to start Postgres, provision the roles and apply the schema. See [README](../../README.md) for the two database URLs.

This guide also covers **forking** any database (remote or local) into a separate local container for development. The source is whatever `DATABASE_ADMIN_URL` is set to in `apps/api/.env` (falling back to `DATABASE_URL` only if that is absent). It has to be the admin URL: the tables `FORCE` row-level security, so only a `BYPASSRLS` role (`renly_admin`) can dump every row.

---

## Quick Start

```bash
pnpm db:fork              # forks into renly-db-local-5433 (default)
pnpm db:fork 5434         # forks into renly-db-local-5434 (second fork)
```

Each port gets its own named container, so you can run multiple forks in parallel.

---

## `.env` Examples

**Remote (Supabase, Railway, etc.):**

```env
DATABASE_URL=postgresql+asyncpg://renly_app:yourpassword@aws-0-us-east-1.pooler.supabase.com:5432/postgres
DATABASE_ADMIN_URL=postgresql+asyncpg://renly_admin:yourpassword@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

**Local docker-compose postgres (port 5432):**

```env
DATABASE_URL=postgresql+asyncpg://renly_app:renly_app@localhost:5432/renly
DATABASE_ADMIN_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:5432/renly
```

**Local fork (after running the script):**

```env
DATABASE_URL=postgresql+asyncpg://renly_app:renly_app@localhost:5433/renly
DATABASE_ADMIN_URL=postgresql+asyncpg://renly_admin:renly_admin@localhost:5433/renly
```

**Typical flow:**

1. Set `.env` to the source you want to fork
2. `pnpm db:fork`
3. Point **both** URLs in `.env` at `localhost:5433` to develop against the fork — leaving one on the source splits the app across two databases (requests on one, the scheduler and logins on the other)
4. Re-sync anytime by pointing `.env` back at the source and re-running

The fork logs in with the same role names as local dev because the script provisions them: it runs [`apps/api/database/00_roles.sql`](../../apps/api/database/00_roles.sql) in the new container (roles are cluster-global, so no dump carries them), then imports the dump **with** its ownership and grants — `renly_app`'s DML grants and the policy helpers' owner (`renly_policy_definer`) arrive exactly as the source has them. The passwords are 00_roles.sql's local defaults, whatever the source's are.

---

## Local Fork Connection Settings

| Field    | Value                                                                      |
| -------- | -------------------------------------------------------------------------- |
| Host     | `127.0.0.1`                                                                |
| Port     | `5433` (or whatever port you passed)                                       |
| Database | `renly`                                                                    |
| App      | `renly_app` / `renly_app` (`DATABASE_URL`)                                 |
| Admin    | `renly_admin` / `renly_admin` (`DATABASE_ADMIN_URL`)                       |
| psql     | `renly` / `renly` — the container's superuser, for inspection, never a URL |

---

## Manual Setup

### Prerequisites

- Docker installed and running
- `DATABASE_ADMIN_URL` set in `apps/api/.env` (the `renly_admin` URL of the source)

### 1. Start local container

```bash
docker run --name renly-db-local-5433 \
  -e POSTGRES_PASSWORD=renly \
  -e POSTGRES_USER=renly \
  -e POSTGRES_DB=renly \
  -p 5433:5432 \
  -d postgres:16-alpine
```

### 2. Provision the roles

```bash
docker exec -i renly-db-local-5433 psql -v ON_ERROR_STOP=1 -U renly -d renly < apps/api/database/00_roles.sql
```

### 3. Dump from source

Replace placeholders with values from your `DATABASE_ADMIN_URL`. Ownership and grants are kept (no `--no-owner` / `--no-acl`): they are the isolation model, and the roles they name now exist in the fork.

```bash
docker run --rm \
  -e PGPASSWORD=<PASSWORD> \
  postgres:16-alpine \
  pg_dump \
    -h <HOST> \
    -p <PORT> \
    -U <USER> \
    -d <DATABASE> \
    --clean \
    --if-exists \
  > dump.sql
```

> If source host is `localhost`, replace it with `host.docker.internal` and add
> `--add-host=host.docker.internal:host-gateway` to the `docker run` args
> (required on Linux; Docker Desktop on Mac handles it automatically).

### 4. Import to local

```bash
docker exec -i renly-db-local-5433 psql -U renly -d renly < dump.sql
```

---

## Verification

```bash
# List tables
docker exec -it renly-db-local-5433 psql -U renly -d renly -c "\dt"

# Quick row count check
docker exec -it renly-db-local-5433 psql -U renly -d renly \
  -c "SELECT schemaname, tablename, n_live_tup FROM pg_stat_user_tables ORDER BY tablename;"
```

---

## Fresh Schema (no data)

**For the main docker-compose Postgres:** use `pnpm db:init` (see README).

For a **standalone** empty local DB (e.g. a fork container) with the correct schema:

```bash
docker run --name renly-db-local-5433 \
  -e POSTGRES_PASSWORD=renly \
  -e POSTGRES_USER=renly \
  -e POSTGRES_DB=renly \
  -p 5433:5432 \
  -d postgres:16-alpine

docker exec -i renly-db-local-5433 psql -U renly -d renly < apps/api/database/00_roles.sql
docker exec -i renly-db-local-5433 psql -U renly -d renly < apps/api/database/01_create_tables.sql
```
