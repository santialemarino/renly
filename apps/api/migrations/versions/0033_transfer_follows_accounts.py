"""hold every transfer to its accounts' scope

Revision ID: 0033_transfer_follows_accounts
Revises: 0032_recon_follows_account
Create Date: 2026-10-28

"""

from alembic import op

revision = "0033_transfer_follows_accounts"
down_revision = "0032_recon_follows_account"
branch_labels = None
depends_on = None

# The same precondition 0030 and 0032 state, for the same reason: handing the function over needs the
# role to exist and the migrating role to be able to act as it, and neither is something a migration
# may create.
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

_FUNCTION = """
CREATE OR REPLACE FUNCTION app_transfer_follows_accounts() RETURNS TRIGGER
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM accounts a
        WHERE a.id IN (NEW.from_account_id, NEW.to_account_id)
          AND (a.user_id IS DISTINCT FROM NEW.user_id OR a.pot_id IS DISTINCT FROM NEW.pot_id)
      ) THEN
        RAISE EXCEPTION 'a transfer must sit in its accounts'' scope (accounts % and %)', NEW.from_account_id, NEW.to_account_id
          USING ERRCODE = 'check_violation', CONSTRAINT = 'transfers_follow_accounts';
      END IF;
      RETURN NEW;
    END
  $$
"""


# A transfer always sits in its accounts' scope: its (user_id, pot_id) is both legs', for every role and
# every write. 0032's rule for reconciliations, for a row with two parents.
#
# The row policies check a transfer against its CALLER and never against its accounts, so an edit that
# re-pointed both legs of a private transfer at one pot's accounts left a private row with pot legs. An
# AFTER INSERT / UPDATE OF user_id, pot_id, from_account_id, to_account_id trigger refuses any row whose
# scope is not both legs', so a scope change happens only by moving the accounts — and the move
# re-points the transfer after them, in the same transaction, where the lookup already reads the new
# scope. Against a concurrent absorption it holds by itself: the foreign keys' KEY SHARE locks wait for
# absorption's FOR UPDATE, and their RI triggers sort ahead of this one by name, so the lookup runs after
# the wait and reads the committed move. transfer_service locks the parent for the moves that only
# UPDATE an account. AFTER, SECURITY DEFINER and owned by renly_policy_definer for 0032's reasons; the
# definer already holds SELECT on the three account columns this body reads, so no grant changes. Same
# statements, same order, as 01_create_tables.sql, so a migrated database and a fresh one dump
# identically.
#
# A trigger checks writes, not the rows already there, so creating it refuses nothing. A row that had
# drifted is still correctable: moving its accounts re-points it to their scope, which is what the
# trigger admits.
def upgrade() -> None:
    op.execute(_PRECONDITION)
    op.execute(_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION app_transfer_follows_accounts() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER trg_transfers_follow_accounts"
        " AFTER INSERT OR UPDATE OF user_id, pot_id, from_account_id, to_account_id ON transfers"
        " FOR EACH ROW EXECUTE FUNCTION app_transfer_follows_accounts()"
    )
    op.execute("GRANT CREATE ON SCHEMA public TO renly_policy_definer")
    op.execute("ALTER FUNCTION app_transfer_follows_accounts() OWNER TO renly_policy_definer")
    op.execute("REVOKE CREATE ON SCHEMA public FROM renly_policy_definer")


# Drops the trigger and its function, restoring 0032 exactly.
def downgrade() -> None:
    op.execute("DROP TRIGGER trg_transfers_follow_accounts ON transfers")
    op.execute("DROP FUNCTION app_transfer_follows_accounts()")
