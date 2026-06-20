# Backups & Restore

Renly's data lives in a single PostgreSQL database, so backups are the last line of defense
against data loss. There are **two layers** (SHELL-4 / INFRA-4):

1. **Supabase automated backups** — the managed platform's built-in backups (enabled at go-live).
2. **`pg_dump` backstop** — a self-managed logical dump (`pnpm db:backup`) that runs on a schedule
   and is portable to any Postgres, independent of the hosting provider.

Both point at the same database. The backstop exists so a restore never depends solely on the
provider's console, and so dumps can be pulled off-platform.

---

## Layer 1 — Supabase automated backups

At go-live, the database is hosted on Supabase. Enable backups in the Supabase dashboard
(**Database → Backups**):

- **Daily backups** are included on paid tiers; retention depends on the plan.
- **Point-in-time recovery (PITR)** is the stronger option (restore to any second within the
  retention window) and is recommended once there are real users.
- Restores are performed from the Supabase dashboard (new project / restore-in-place per their
  flow). Follow Supabase's restore docs for the exact steps for the active plan.

Supabase backups are managed entirely on the platform — there is nothing to configure in this
repo for them beyond turning them on.

---

## Layer 2 — `pg_dump` backstop (`pnpm db:backup`)

A compressed logical dump created with a throwaway `postgres:16-alpine` container (no host
`pg_dump` needed). Output goes to `backups/renly-<YYYYMMDD-HHMMSS>.sql.gz` (the `backups/`
directory is gitignored).

```bash
# Source resolution (first match wins):
#   1. $BACKUP_DATABASE_URL
#   2. DATABASE_ADMIN_URL in apps/api/.env   (table owner — bypasses RLS, dumps ALL rows)
#   3. DATABASE_URL in apps/api/.env         (restricted RLS role → dumps ZERO user rows; warns)
pnpm db:backup

# Or point it at production explicitly:
BACKUP_DATABASE_URL='postgresql://OWNER:PASS@HOST:PORT/DB' pnpm db:backup
```

> **Critical (RLS):** the backup must connect as the **table owner**, not the restricted `renly_app`
> role. With Row-Level Security enabled (SEC-15) and no `app.current_user_id` set, the restricted
> role sees **zero rows**, so a dump taken as `renly_app` would back up an empty database. The
> script prefers `DATABASE_ADMIN_URL` for this reason and warns if it falls back to `DATABASE_URL`.

The dump uses `--no-owner --no-acl --clean --if-exists`, making it portable to a fresh Postgres
(ownership/role grants are not embedded — see the role caveat under Restore).

### Scheduling the backstop (production)

Run `pnpm db:backup` on a schedule on the host (e.g. a daily cron job or the platform's scheduled
task), with `BACKUP_DATABASE_URL` set to the production owner URL, and copy the resulting
`backups/*.sql.gz` to off-platform storage (e.g. object storage). This is a backstop to the
Supabase backups, not a replacement for them.

---

## Restore (`pnpm db:restore`)

```bash
RESTORE_DATABASE_URL='postgresql://OWNER:PASS@HOST:PORT/DB' \
  pnpm db:restore backups/renly-<timestamp>.sql.gz --force
```

- **Destructive.** The dump is `--clean --if-exists`, so matching objects in the target are
  dropped and recreated. The target is taken **only** from `$RESTORE_DATABASE_URL` (never
  `DATABASE_URL`, to avoid clobbering your dev DB), and `--force` is required.
- Restore **as the table owner** (`psql` runs with `ON_ERROR_STOP=1`).
- **Role caveat:** `pg_dump` does not include roles, and `--no-acl` omits grants. When restoring
  into a **brand-new** database, the restricted `renly_app` role and its grants are not recreated.
  Re-provision them by re-running the role/grant section of
  [`apps/api/database/01_create_tables.sql`](../../apps/api/database/01_create_tables.sql) (the
  `CREATE ROLE renly_app … / GRANT …` block), then point `DATABASE_URL` at `renly_app`. The RLS
  policies and the `app_current_user_id()` function themselves **are** in the dump and restore
  automatically.

---

## Rehearsed restore

A restore was rehearsed end-to-end against throwaway containers (the shared dev `renly-postgres`
is never touched):

1. Spin a **source** container, apply `01_create_tables.sql`, seed a user + an investment.
2. `BACKUP_DATABASE_URL=…source… pnpm db:backup` → `backups/renly-<ts>.sql.gz`.
3. Spin an **empty target** container.
4. `RESTORE_DATABASE_URL=…target… pnpm db:restore <file> --force`.
5. Compare the target against the source.

**Verified result:** the target matched the source exactly — `users=1`, `investments=1`, all 19
tables present, the seeded rows round-tripped, all **16 RLS policies** restored, and
`relrowsecurity` stayed `true` on the user-scoped tables. `psql` ran clean under `ON_ERROR_STOP=1`.

Re-run this rehearsal whenever the schema changes materially (new tables, new RLS policies) to
confirm dumps still restore cleanly.
