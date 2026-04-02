# Local Database Setup Guide

**First-time DB (docker-compose):** From repo root, run `pnpm db:init` to start Postgres and apply the schema. See [README](../README.md) for `DATABASE_URL`.

This guide also covers **forking** any database (remote or local) into a separate local container for development. The source is always whatever `DATABASE_URL` is set to in `apps/api/.env`.

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
DATABASE_URL=postgresql+asyncpg://postgres.xxxx:yourpassword@aws-0-us-east-1.pooler.supabase.com:5432/postgres
```

**Local docker-compose postgres (port 5432):**

```env
DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5432/renly
```

**Local fork (after running the script):**

```env
DATABASE_URL=postgresql+asyncpg://renly:renly@localhost:5433/renly
```

**Typical flow:**

1. Set `.env` to the source you want to fork
2. `pnpm db:fork`
3. Update `.env` to `localhost:5433` to develop against the fork
4. Re-sync anytime by pointing `.env` back at the source and re-running

---

## Local Fork Connection Settings

| Field    | Value                                |
| -------- | ------------------------------------ |
| Host     | `127.0.0.1`                          |
| Port     | `5433` (or whatever port you passed) |
| Database | `renly`                              |
| User     | `renly`                              |
| Password | `renly`                              |

---

## Manual Setup

### Prerequisites

- Docker installed and running
- `DATABASE_URL` set in `apps/api/.env`

### 1. Start local container

```bash
docker run --name renly-db-local-5433 \
  -e POSTGRES_PASSWORD=renly \
  -e POSTGRES_USER=renly \
  -e POSTGRES_DB=renly \
  -p 5433:5432 \
  -d postgres:16-alpine
```

### 2. Dump from source

Replace placeholders with values from your `DATABASE_URL`.

```bash
docker run --rm \
  -e PGPASSWORD=<PASSWORD> \
  postgres:16-alpine \
  pg_dump \
    -h <HOST> \
    -p <PORT> \
    -U <USER> \
    -d <DATABASE> \
    --no-owner \
    --no-acl \
    --clean \
    --if-exists \
  > dump.sql
```

> If source host is `localhost`, replace it with `host.docker.internal` and add
> `--add-host=host.docker.internal:host-gateway` to the `docker run` args
> (required on Linux; Docker Desktop on Mac handles it automatically).

### 3. Import to local

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

docker exec -i renly-db-local-5433 psql -U renly -d renly < apps/api/database/01_create_tables.sql
```
