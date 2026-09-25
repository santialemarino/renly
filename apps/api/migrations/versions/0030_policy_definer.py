"""hand the security-definer policy helpers to a bypass role, and grant renly_app what migrations create

Revision ID: 0030_policy_definer
Revises: 0029_rls_force
Create Date: 2026-09-25

"""

from alembic import op

revision = "0030_policy_definer"
down_revision = "0029_rls_force"
branch_labels = None
depends_on = None


# The three SECURITY DEFINER helpers the policies call. A policy on group_members calls
# app_is_group_member(), which reads group_members — so whoever the helper runs as must not be subject
# to that policy, or it re-enters itself until "stack depth limit exceeded".
_HELPERS = (
    "app_can_view_pot(BIGINT)",
    "app_can_write_pot(BIGINT)",
    "app_is_group_member(BIGINT)",
)

# Exactly the tables those three bodies read, and nothing else.
_READS = "pots, group_members, pot_member_permissions"

# Refuses to start without the role, rather than creating it. Roles are cluster-global and CREATE ROLE
# needs CREATEROLE, which renly_admin (who runs migrations) deliberately lacks — so a migration that
# tried would work on a superuser's laptop and fail everywhere it matters. 00_roles.sql is the one
# place roles are defined; this names it. Membership is checked for the same reason: handing a
# function to a role requires being able to SET ROLE to it, and only a superuser can grant that.
_PRECONDITION = """
    DO $$ BEGIN
      IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_policy_definer') THEN
        RAISE EXCEPTION 'role renly_policy_definer does not exist'
          USING HINT = 'Run apps/api/database/00_roles.sql as a superuser against this database, then re-run the migration.';
      END IF;
      IF NOT pg_has_role(CURRENT_USER, 'renly_policy_definer', 'MEMBER') THEN
        RAISE EXCEPTION '% cannot act as renly_policy_definer', CURRENT_USER
          USING HINT = 'Run apps/api/database/00_roles.sql as a superuser against this database (it makes the owner, and through it renly_admin, a member), then re-run the migration.';
      END IF;
    END $$
"""


# Fixes the helpers #220's FORCE broke on any database whose owner is not a superuser.
#
# Under FORCE the owner is subject to the policies, and until now the owner WAS who the helpers ran
# as: every read of a group, a roster or a pot recursed until the stack ran out. A superuser owner
# bypasses RLS regardless, which is why no local database ever showed it. The helpers move to
# renly_policy_definer — NOLOGIN, BYPASSRLS, not a superuser, and SELECT on only the three tables
# they read — so every table stays FORCEd and the bypass reaches no further than those questions.
#
# CREATE on the schema is required of a function's new owner at handover and of nothing afterwards, so
# it is granted for the ALTER and revoked straight after.
#
# ▸ Also fixes grants for tables FUTURE migrations create. Those are created by renly_admin, and the
# owner's default privileges do not cover them; `env.py` reassigns their ownership afterwards, but
# REASSIGN OWNED moves ownership and adds no privilege, so renly_app would reach a new table with
# nothing. renly_admin may declare default privileges for itself, so it does so here; 00_roles.sql
# declares the same for a database built from the script.
#
# Same statements, same order, as 01_create_tables.sql, so a migrated database and a fresh one dump
# identically.
def upgrade() -> None:
    op.execute(_PRECONDITION)
    op.execute("GRANT USAGE ON SCHEMA public TO renly_policy_definer")
    op.execute(f"GRANT SELECT ON {_READS} TO renly_policy_definer")
    op.execute("GRANT CREATE ON SCHEMA public TO renly_policy_definer")
    for helper in _HELPERS:
        op.execute(f"ALTER FUNCTION {helper} OWNER TO renly_policy_definer")
    op.execute("REVOKE CREATE ON SCHEMA public FROM renly_policy_definer")

    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE renly_admin IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO renly_app")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE renly_admin IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO renly_app")


# Hands the helpers back to the table owner (read from `users`, the same anchor `env.py` uses) and
# withdraws what this revision granted. That restores 0029 exactly — including its defect on a
# NOSUPERUSER owner, which is what 0029 is. The ROLE and its memberships are left in place: they are
# cluster-global, belong to 00_roles.sql rather than to this chain, and a role that owns nothing and
# may read nothing costs nothing.
def downgrade() -> None:
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE renly_admin IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM renly_app")
    op.execute("ALTER DEFAULT PRIVILEGES FOR ROLE renly_admin IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM renly_app")

    owner = op.get_bind().exec_driver_sql("SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'public.users'::regclass").scalar_one()
    for helper in _HELPERS:
        op.execute(f'ALTER FUNCTION {helper} OWNER TO "{owner}"')
    op.execute(f"REVOKE SELECT ON {_READS} FROM renly_policy_definer")
    op.execute("REVOKE USAGE ON SCHEMA public FROM renly_policy_definer")
