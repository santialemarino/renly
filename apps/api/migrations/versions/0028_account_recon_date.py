"""one account reconciliation per date, so same-date re-runs replace instead of stacking

Revision ID: 0028_account_recon_date
Revises: 0027_digests_plan_events
Create Date: 2026-09-20

"""

from alembic import op

revision = "0028_account_recon_date"
down_revision = "0027_digests_plan_events"
branch_labels = None
depends_on = None

_CONSTRAINT = "account_reconciliations_account_date_key"
_REDUNDANT_INDEX = "idx_account_reconciliations_account_date"


# Makes (account_id, as_of_date) unique, which is what turns re-reconciling a date into a replace.
#
# The delete guard in account_reconciliation_service compares DATES — "only the latest reconciliation
# may be deleted" is `as_of_date < max(as_of_date)`. Two rows sharing a date were therefore both the
# latest and both deletable, and deleting the older one dropped its adjustment while the survivor's
# recorded computed_balance still counted it: the account ended up wrong by that whole adjustment,
# with no row left that could explain the gap. The constraint removes the case rather than adding a
# tie-break, so the guard is exact by construction.
#
# It REFUSES rather than collapsing when duplicates already exist, and that is deliberate. Collapsing
# correctly means keeping the newest row's statement_balance, restoring the OLDEST row's
# computed_balance (the only one taken before any same-date adjustment existed), re-signing the merged
# adjustment — which can flip between an income and an expense — and, on a pot's account, re-splitting
# it across the owners at their proportions on that date. That is balance-moving logic with no test
# data to exercise it, so a wrong collapse would silently restate money. Refusing leaves the operator
# with an intact database and a query that names every offending pair.
#
# The redundant index goes with it: the constraint builds a btree on the same pair, and Postgres scans
# a btree backwards, so it already serves both the newest-first history read and the max(as_of_date)
# lookup the old DESC index was created for.
def upgrade() -> None:
    duplicates = op.get_bind().exec_driver_sql(
        "SELECT account_id, as_of_date, count(*) FROM account_reconciliations"
        " GROUP BY account_id, as_of_date HAVING count(*) > 1 ORDER BY account_id, as_of_date"
    ).fetchall()
    if duplicates:
        listed = ", ".join(f"account {account_id} on {as_of_date} ({count} rows)" for account_id, as_of_date, count in duplicates)
        raise RuntimeError(
            "account_reconciliations holds rows that share an (account_id, as_of_date) pair, so the"
            f" uniqueness this revision introduces cannot be applied: {listed}."
            " Resolve each pair by hand before upgrading — keep the newest row's statement_balance,"
            " restore the oldest row's computed_balance, and re-post a single adjustment for the"
            " difference between them."
        )

    op.execute(f"DROP INDEX IF EXISTS {_REDUNDANT_INDEX}")
    op.execute(f"ALTER TABLE account_reconciliations ADD CONSTRAINT {_CONSTRAINT} UNIQUE (account_id, as_of_date)")


# Restores the DESC index the constraint replaced, so a downgraded database keeps the access path the
# history read was built against. Nothing is lost by dropping the constraint: rows written under it
# satisfy the weaker shape too.
def downgrade() -> None:
    op.execute(f"ALTER TABLE account_reconciliations DROP CONSTRAINT IF EXISTS {_CONSTRAINT}")
    op.execute(f"CREATE INDEX IF NOT EXISTS {_REDUNDANT_INDEX} ON account_reconciliations(account_id, as_of_date DESC)")
