"""hold every account reconciliation to its account's scope

Revision ID: 0032_recon_follows_account
Revises: 0031_recon_scope_grant
Create Date: 2026-09-27

"""

from alembic import op

revision = "0032_recon_follows_account"
down_revision = "0031_recon_scope_grant"
branch_labels = None
depends_on = None

# Exactly what the function body reads, and nothing else.
_READS = "(id, user_id, pot_id) ON accounts"

# The same precondition 0030 states, for the same reason: handing the function over needs the role to
# exist and the migrating role to be able to act as it, and neither is something a migration may create.
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
CREATE OR REPLACE FUNCTION app_reconciliation_follows_account() RETURNS TRIGGER
  LANGUAGE plpgsql SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    DECLARE
      account_user_id BIGINT;
      account_pot_id BIGINT;
    BEGIN
      SELECT a.user_id, a.pot_id INTO account_user_id, account_pot_id FROM accounts a WHERE a.id = NEW.account_id;
      IF NOT FOUND THEN
        RETURN NEW;
      END IF;
      IF NEW.user_id IS DISTINCT FROM account_user_id OR NEW.pot_id IS DISTINCT FROM account_pot_id THEN
        RAISE EXCEPTION 'a reconciliation must sit in its account''s scope (account %)', NEW.account_id
          USING ERRCODE = 'check_violation', CONSTRAINT = 'account_reconciliations_follow_account';
      END IF;
      RETURN NEW;
    END
  $$
"""


# A reconciliation always sits in its account's scope, for every role and every write.
#
# The row policies check a reconciliation against its CALLER and never against its account, so as the
# request role a view-only co-owner could re-point a pot's reconciliation into their own private scope
# (0031 granted the scope pair for account moves), record a pot-scoped one naming another user's private
# account, or a private one on a pot's account. An AFTER INSERT / UPDATE OF user_id, pot_id, account_id
# trigger refuses any row whose scope is not its account's, so a scope change happens only by moving the
# account — which needs pot write access — and the move re-points the children after the account, in the
# same transaction, where the lookup already reads the new scope. One path does not use that move yet:
# account deletion absorbing an orphaned group's pots (reassign_pots_to_user) re-points the accounts but
# not their reconciliations, which a trigger on account_reconciliations cannot see; the rows it leaves
# out of scope are deleted with the user right after, unless deletion fails in between. The lookup takes no lock, so two
# concurrent transactions could still break it — a private reconciliation inserted, uncommitted, while
# the account moves into a pot and its re-point matches nothing — and it holds at the API level because
# the services serialise both sides first: a reconcile takes lock_private (the account, FOR UPDATE) or
# the pot's lock, and a move locks the pot and then updates the account. AFTER rather than BEFORE so it only
# judges rows the policies already admitted: ahead of their WITH CHECK, which error answered would tell a
# caller whether a guess at the scope of an account they cannot see was right.
#
# SECURITY DEFINER because the account may be one the caller cannot see, and owned by
# renly_policy_definer with SELECT on the three columns it reads, for the reason 0030 gives: a function
# the owner owned would be subject to the FORCEd policies. Same statements, same order, as
# 01_create_tables.sql, so a migrated database and a fresh one dump identically.
#
# A trigger checks writes, not the rows already there, so creating it refuses nothing. A row that had
# drifted is still correctable: an account move re-points its children to the account's scope, which is
# exactly what the trigger admits.
def upgrade() -> None:
    op.execute(_PRECONDITION)
    op.execute(_FUNCTION)
    op.execute("REVOKE ALL ON FUNCTION app_reconciliation_follows_account() FROM PUBLIC")
    op.execute(
        "CREATE TRIGGER trg_account_reconciliations_follow_account"
        " AFTER INSERT OR UPDATE OF user_id, pot_id, account_id ON account_reconciliations"
        " FOR EACH ROW EXECUTE FUNCTION app_reconciliation_follows_account()"
    )
    op.execute(f"GRANT SELECT {_READS} TO renly_policy_definer")
    op.execute("GRANT CREATE ON SCHEMA public TO renly_policy_definer")
    op.execute("ALTER FUNCTION app_reconciliation_follows_account() OWNER TO renly_policy_definer")
    op.execute("REVOKE CREATE ON SCHEMA public FROM renly_policy_definer")


# Drops the trigger and its function and withdraws the column grant, restoring 0031 exactly.
def downgrade() -> None:
    op.execute("DROP TRIGGER trg_account_reconciliations_follow_account ON account_reconciliations")
    op.execute("DROP FUNCTION app_reconciliation_follows_account()")
    op.execute(f"REVOKE SELECT {_READS} FROM renly_policy_definer")
