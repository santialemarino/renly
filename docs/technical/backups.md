# Backups & Restore

Renly's data lives in a single PostgreSQL database, so backups are the last line of defense
against data loss. The repo provides a **`pg_dump`-based backup + a rehearsed restore** that works
against any PostgreSQL, independent of the hosting provider, so a restore never depends on a
specific platform's console. If the managed Postgres host chosen at go-live also offers its own
automated backups (daily snapshots / point-in-time recovery), enable those as an additional layer.

---

## Backup (`pnpm db:backup`)

A compressed logical dump created with a throwaway `postgres:16-alpine` container (no host
`pg_dump` needed). Output goes to `backups/renly-<YYYYMMDD-HHMMSS>.sql.gz` (the `backups/`
directory is gitignored).

```bash
# Source resolution (first match wins):
#   1. $BACKUP_DATABASE_URL
#   2. DATABASE_ADMIN_URL in apps/api/.env   (renly_admin — BYPASSRLS, dumps ALL rows)
#   3. DATABASE_URL in apps/api/.env         (restricted RLS role → dumps ZERO user rows; warns)
pnpm db:backup

# Or point it at production explicitly:
BACKUP_DATABASE_URL='postgresql://renly_admin:PASS@HOST:PORT/DB' pnpm db:backup
```

> **Critical (RLS):** the backup must connect as **`renly_admin`** — the role with `BYPASSRLS` —
> and not as `renly_app` or as the owner. With Row-Level Security enabled (SEC-15) and no
> `app.current_user_id` set, a role subject to the policies sees **zero rows**, so the dump would be
> of an empty database. Since the tables also carry `FORCE ROW LEVEL SECURITY`, **owning them is not
> an exemption**: a dump taken as `renly` is just as empty as one taken as `renly_app`. The bypass has
> to come from the role attribute.
>
> `pg_dump` does fail loudly under `FORCE` rather than writing an empty file — it exits 1 with
> `query would be affected by row-level security policy` and a `HINT` naming the cause — so a wrong
> role produces no backup rather than a useless one. The script prefers `DATABASE_ADMIN_URL` for this
> reason and warns if it falls back to `DATABASE_URL`.

The dump uses `--no-owner --no-acl --clean --if-exists`, making it portable to a fresh Postgres
(ownership/role grants are not embedded — see the role caveat under Restore).

### Scheduling (production)

Run `pnpm db:backup` on a schedule on the host (e.g. a daily cron job or the platform's scheduled
task), with `BACKUP_DATABASE_URL` set to the production owner URL, and copy the resulting
`backups/*.sql.gz` to off-platform storage (e.g. object storage). Treat this as the primary,
host-independent backup; any provider-native backups complement it.

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
  into a **brand-new** database, neither `renly_admin` nor `renly_app` is recreated and neither
  carries its grants. Re-provision both by re-running the role/grant section of
  [`apps/api/database/01_create_tables.sql`](../../apps/api/database/01_create_tables.sql), then
  point `DATABASE_URL` at `renly_app` and `DATABASE_ADMIN_URL` at `renly_admin`. The RLS policies,
  the `FORCE` flags and the `app_current_user_id()` function themselves **are** in the dump and
  restore automatically — which means a restored database is FORCEd from the first moment, and
  reading it needs `renly_admin` rather than whoever ran the restore.

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
