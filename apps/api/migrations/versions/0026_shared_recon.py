"""a shared account's reconciliation, and where its adjustment lives

Revision ID: 0026_shared_recon
Revises: 0025_reagreement_confirm
Create Date: 2026-09-13

"""

import sqlalchemy as sa
from alembic import op

revision = "0026_shared_recon"
down_revision = "0025_reagreement_confirm"
branch_labels = None
depends_on = None

# The view predicate, which is what reconciling is gated on — not the write one this table used until
# now. Reconciling a pot's account requires only that the pot be VISIBLE, the same gate the equivalent
# manual act carries: a shared expense drawn from that account needs group membership and a visible,
# divided pot, never pot write access. A policy keyed on app_can_write_pot therefore refuses the exact
# read-only co-owner the service admits, which is two halves of one rule disagreeing — and it fails the
# way RLS always does, as a bare "new row violates row-level security policy".
_VISIBLE = "user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_view_pot(pot_id))"

# The FOR ALL this replaces governed SELECT, INSERT, UPDATE and DELETE on pot WRITE access. Split per
# command because only one of them needs capping: the service patches its own back-pointer immediately
# after inserting, so UPDATE has to admit whoever may reconcile — and admitting them to the WHOLE row
# would let a read-only seat rewrite a statement balance somebody else recorded, leaving the
# reconciliation claiming a difference its adjustment does not match. The column grant below is what
# stops that, because RLS filters rows and never columns.
#
# No WITH CHECK on the update: Postgres reuses the USING expression when one is absent, so the row must
# qualify before and after either way, and nothing the predicate reads is writable.
_SCOPE_SPLIT = (
    f"CREATE POLICY account_reconciliations_scope_insert ON account_reconciliations FOR INSERT WITH CHECK ({_VISIBLE})",
    f"CREATE POLICY account_reconciliations_scope_update ON account_reconciliations FOR UPDATE USING ({_VISIBLE})",
    f"CREATE POLICY account_reconciliations_scope_delete ON account_reconciliations FOR DELETE USING ({_VISIBLE})",
)

# The four back-pointer columns and nothing else. Column privileges are checked against a statement's
# SET list, and the BEFORE UPDATE trigger writes NEW.updated_at with no privilege of the invoking role —
# so `updated_at` is deliberately absent, and the narrower grant fails loudly if that stops being true.
_ADJUSTMENT_COLUMNS = "adjustment_expense_id, adjustment_income_id, adjustment_shared_expense_id, adjustment_shared_income_id"


# Makes a pot's account reconcilable by giving the reconciliation somewhere to put its adjustment.
#
# account_reconciliations already carried pot_id, the single-owner CHECK and the dual-scope policies, so
# the parent's columns needed little. What was missing is the adjustment: expense_entries /
# income_entries keep user_id NOT NULL and carry no pot_id at all (§3 — a shared flow lives in its own
# table), and the pot account's balance sums filter on that same user_id — so a private adjustment row
# naming a pot-owned account would not close the drift it exists to close. The shared adjustment is
# therefore a shared_expenses / shared_income row, which those sums already count in full.
#
# Nothing is backfilled beyond created_by, and no balance moves: every existing reconciliation is
# private, and the four new columns are NULL on all of them.
def upgrade() -> None:
    op.add_column("account_reconciliations", sa.Column("adjustment_shared_expense_id", sa.BigInteger(), nullable=True))
    op.add_column("account_reconciliations", sa.Column("adjustment_shared_income_id", sa.BigInteger(), nullable=True))
    op.add_column("account_reconciliations", sa.Column("created_by", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "account_reconciliations_created_by_fkey",
        "account_reconciliations",
        "users",
        ["created_by"],
        ["id"],
        ondelete="SET NULL",
    )
    # Every existing row is private, so its owner IS whoever ran it. Backfilled rather than left NULL
    # because a NULL here means "the account is gone" on a shared row, and a private row that never had
    # a creator would read as that same thing.
    op.execute("UPDATE account_reconciliations SET created_by = user_id WHERE created_by IS NULL")

    op.add_column("shared_expenses", sa.Column("account_reconciliation_id", sa.BigInteger(), nullable=True))
    op.add_column("shared_income", sa.Column("account_reconciliation_id", sa.BigInteger(), nullable=True))

    # The closed loop, in both directions and with the asymmetry the private pair already has. CASCADE
    # from the flow row's side is what makes deleting a reconciliation remove the adjustment it created
    # — the escape hatch for a mistyped balance. SET NULL from the reconciliation's side is only a
    # safety net for an out-of-band delete: the endpoints refuse a direct delete of a
    # reconciliation-owned row, because clearing this pointer would leave the reconciliation claiming a
    # difference it no longer applies while the balance snapped back.
    op.create_foreign_key(
        "shared_expenses_account_reconciliation_fkey",
        "shared_expenses",
        "account_reconciliations",
        ["account_reconciliation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "shared_income_account_reconciliation_fkey",
        "shared_income",
        "account_reconciliations",
        ["account_reconciliation_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "account_reconciliations_adjustment_shared_expense_fkey",
        "account_reconciliations",
        "shared_expenses",
        ["adjustment_shared_expense_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "account_reconciliations_adjustment_shared_income_fkey",
        "account_reconciliations",
        "shared_income",
        ["adjustment_shared_income_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute(
        "CREATE INDEX idx_shared_expenses_account_reconciliation_id"
        " ON shared_expenses(account_reconciliation_id) WHERE account_reconciliation_id IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX idx_shared_income_account_reconciliation_id"
        " ON shared_income(account_reconciliation_id) WHERE account_reconciliation_id IS NOT NULL"
    )

    # Each scope may only carry its own kind of adjustment. Stated as a constraint rather than left to
    # the service so it holds for the privileged session too, and so a row read back says which kind of
    # adjustment to look for from its scope alone.
    op.create_check_constraint(
        "account_reconciliations_private_adjustment",
        "account_reconciliations",
        "pot_id IS NULL OR (adjustment_expense_id IS NULL AND adjustment_income_id IS NULL)",
    )
    op.create_check_constraint(
        "account_reconciliations_shared_adjustment",
        "account_reconciliations",
        "user_id IS NULL OR (adjustment_shared_expense_id IS NULL AND adjustment_shared_income_id IS NULL)",
    )

    # And the rule the DATABASE has to hold too: who may write one of these rows.
    op.execute("DROP POLICY IF EXISTS account_reconciliations_scope_write ON account_reconciliations")
    for statement in _SCOPE_SPLIT:
        op.execute(statement)
    op.execute("REVOKE UPDATE ON account_reconciliations FROM renly_app")
    op.execute(f"GRANT UPDATE ({_ADJUSTMENT_COLUMNS}) ON account_reconciliations TO renly_app")


# Drops the shared adjustment's columns and the creator.
#
# Down-migrating a database that holds a SHARED reconciliation orphans its adjustment: the flow row
# survives with its link column gone, so the money stays out of the account and the reconciliation row
# that explained it no longer points at anything. That is the honest outcome — deleting the adjustment
# instead would silently move a balance during a schema change — and it is why this is a one-way door
# in practice. A PRIVATE reconciliation loses nothing: `created_by` equals `user_id` on every one of
# them, by the backfill above and by what the service writes, so the dropped column is re-derivable.
def downgrade() -> None:
    # The per-column grant goes before the table-level one is restored, so the role never holds both.
    op.execute(f"REVOKE UPDATE ({_ADJUSTMENT_COLUMNS}) ON account_reconciliations FROM renly_app")
    op.execute("GRANT UPDATE ON account_reconciliations TO renly_app")
    op.execute("DROP POLICY IF EXISTS account_reconciliations_scope_delete ON account_reconciliations")
    op.execute("DROP POLICY IF EXISTS account_reconciliations_scope_update ON account_reconciliations")
    op.execute("DROP POLICY IF EXISTS account_reconciliations_scope_insert ON account_reconciliations")
    op.execute(
        "CREATE POLICY account_reconciliations_scope_write ON account_reconciliations FOR ALL"
        " USING (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))"
        " WITH CHECK (user_id = app_current_user_id() OR (pot_id IS NOT NULL AND app_can_write_pot(pot_id)))"
    )
    op.drop_constraint("account_reconciliations_shared_adjustment", "account_reconciliations", type_="check")
    op.drop_constraint("account_reconciliations_private_adjustment", "account_reconciliations", type_="check")
    op.execute("DROP INDEX IF EXISTS idx_shared_income_account_reconciliation_id")
    op.execute("DROP INDEX IF EXISTS idx_shared_expenses_account_reconciliation_id")
    op.drop_constraint("account_reconciliations_adjustment_shared_income_fkey", "account_reconciliations", type_="foreignkey")
    op.drop_constraint("account_reconciliations_adjustment_shared_expense_fkey", "account_reconciliations", type_="foreignkey")
    op.drop_constraint("shared_income_account_reconciliation_fkey", "shared_income", type_="foreignkey")
    op.drop_constraint("shared_expenses_account_reconciliation_fkey", "shared_expenses", type_="foreignkey")
    op.drop_column("shared_income", "account_reconciliation_id")
    op.drop_column("shared_expenses", "account_reconciliation_id")
    op.drop_constraint("account_reconciliations_created_by_fkey", "account_reconciliations", type_="foreignkey")
    op.drop_column("account_reconciliations", "created_by")
    op.drop_column("account_reconciliations", "adjustment_shared_income_id")
    op.drop_column("account_reconciliations", "adjustment_shared_expense_id")
