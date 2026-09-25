"""force row level security on every policied table, and the bypass role that makes it survivable

Revision ID: 0029_rls_force
Revises: 0028_account_recon_date
Create Date: 2026-09-24

"""

from alembic import op

revision = "0029_rls_force"
down_revision = "0028_account_recon_date"
branch_labels = None
depends_on = None


# Every table this migration FORCEs. Derived from the live catalogue rather than listed, so the set is
# whatever actually has RLS enabled at the moment it runs — a table added between this being written
# and being applied is covered, and one that is not policied is not touched.
_ENABLED = """
    SELECT c.relname
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relrowsecurity AND NOT c.relforcerowsecurity
    ORDER BY c.relname
"""


# Adds the third role and subjects the owner to its own policies.
#
# Until now the owner bypassed RLS simply by owning the tables, and that was load-bearing: the
# scheduler, the pre-auth users lookup and every data backfill in these migrations legitimately span
# users. FORCE removes that exemption, so the work moves to `renly_admin` — BYPASSRLS, not a
# superuser, and a member of the owner so it can still alter owner-owned objects.
#
# What FORCE buys is narrow and real: a connection pointed at the OWNER now reads nothing instead of
# everything. That is not hypothetical — local dev ran that way for months with every policy inert,
# and `deployment.md` instructed operators to do the same for migrations.
#
# ▸ The role is created here as well as in `01_create_tables.sql` because roles are CLUSTER-global
# while migrations are per-database: a database built from the script has it, an existing one upgraded
# through this chain does not. Both spellings guard on existence for exactly that reason.
def upgrade() -> None:
    bind = op.get_bind()

    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_admin') THEN
            CREATE ROLE renly_admin LOGIN PASSWORD 'renly_admin' NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
          END IF;
        END $$
        """
    )
    # CURRENT_USER rather than a literal: whoever owns these tables is who renly_admin has to be able
    # to act for, and on a developer machine that is not necessarily named `renly`. Wrapped because a
    # re-run, or a cluster where the grant already exists, is not a failure.
    op.execute(
        """
        DO $$ BEGIN
          EXECUTE format('GRANT %I TO renly_admin', CURRENT_USER);
        EXCEPTION WHEN OTHERS THEN
          RAISE NOTICE 'could not grant % to renly_admin: %', CURRENT_USER, SQLERRM;
        END $$
        """
    )
    op.execute("GRANT USAGE ON SCHEMA public TO renly_admin")

    for (table,) in bind.exec_driver_sql(_ENABLED).fetchall():
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")


# Lifts FORCE back off, leaving ENABLE — the two-role shape, where owning a table is enough to bypass
# its policies. The ROLE is deliberately left in place: it is cluster-global, other databases on the
# same cluster may be using it, and a role that owns nothing costs nothing. Dropping it would also
# strand any connection string still pointing at it, which is the opposite of what a downgrade is for.
def downgrade() -> None:
    bind = op.get_bind()
    forced = """
        SELECT c.relname
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r' AND c.relforcerowsecurity
        ORDER BY c.relname
    """
    for (table,) in bind.exec_driver_sql(forced).fetchall():
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
