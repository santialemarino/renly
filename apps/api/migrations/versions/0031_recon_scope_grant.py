"""let renly_app re-point an account's reconciliations when the account changes scope

Revision ID: 0031_recon_scope_grant
Revises: 0030_policy_definer
Create Date: 2026-09-27

"""

from alembic import op

revision = "0031_recon_scope_grant"
down_revision = "0030_policy_definer"
branch_labels = None
depends_on = None

# The two scope columns account_reconciliations denormalizes from its account.
_SCOPE_COLUMNS = "user_id, pot_id"


# Adds the scope pair to renly_app's per-column UPDATE grant on account_reconciliations.
#
# 0026 capped that grant at the four adjustment back-pointers, but moving an account into or out of a
# pot re-points its reconciliations' user_id / pot_id in the same statement set as the account, so as
# the request role every such move answered "permission denied" — for accounts with no reconciliation
# too, since Postgres checks a column privilege against the statement rather than the rows it matches.
# The amounts stay out of the grant. The row policy still bounds both ends of a re-point: its USING
# picks the rows the caller may touch, and with no WITH CHECK Postgres holds the NEW row to that same
# predicate, so a reconciliation can move only between scopes its caller can see.
#
# GRANT is idempotent, so a database that already carries it is unchanged.
def upgrade() -> None:
    op.execute(f"GRANT UPDATE ({_SCOPE_COLUMNS}) ON account_reconciliations TO renly_app")


# Takes the scope pair back out of the grant, leaving the four back-pointers as 0026 left them.
def downgrade() -> None:
    op.execute(f"REVOKE UPDATE ({_SCOPE_COLUMNS}) ON account_reconciliations FROM renly_app")
