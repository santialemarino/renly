"""account reconciliations: point-in-time balance true-up (Bucket 3 #1, PR 4)

Revision ID: 0012_account_reconciliations
Revises: 0011_account_links
Create Date: 2026-07-29

"""

import sqlalchemy as sa
from alembic import op

revision = "0012_account_reconciliations"
down_revision = "0011_account_links"
branch_labels = None
depends_on = None

# Money tables gaining the cascade link back to the reconciliation that created their adjustment row.
_ENTRY_TABLES = ("expense_entries", "income_entries")


# Creates the account_reconciliations table (the cash/bank sibling of card_reconciliations, simplified
# to a point-in-time balance: no statement period, no currency bucket, no is_stale), adds the
# account_adjustment category to both entry enums so reconciliation adjustments stay filterable, and
# wires the ON DELETE CASCADE link from each entry table so deleting a reconciliation also removes the
# adjustment it created.
def upgrade() -> None:
    # BEFORE 'other' keeps 'other' last, matching the fresh-build enum order in 01_create_tables.sql.
    # IF NOT EXISTS keeps the migration idempotent. Safe inside Alembic's transaction on PostgreSQL 12+
    # because the migration only declares the values — nothing writes a row using them here.
    op.execute("ALTER TYPE expense_category ADD VALUE IF NOT EXISTS 'account_adjustment' BEFORE 'other'")
    op.execute("ALTER TYPE income_category ADD VALUE IF NOT EXISTS 'account_adjustment' BEFORE 'other'")

    op.create_table(
        "account_reconciliations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column("statement_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("computed_balance", sa.Numeric(18, 2), nullable=False),
        sa.Column("difference", sa.Numeric(18, 2), nullable=False),
        sa.Column("adjustment_expense_id", sa.BigInteger(), sa.ForeignKey("expense_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("adjustment_income_id", sa.BigInteger(), sa.ForeignKey("income_entries.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reconciled_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_account_reconciliations_user_id", "account_reconciliations", ["user_id"])
    op.create_index(
        "idx_account_reconciliations_account_date",
        "account_reconciliations",
        ["account_id", sa.text("as_of_date DESC")],
    )

    for table in _ENTRY_TABLES:
        op.add_column(table, sa.Column("account_reconciliation_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            f"{table}_account_reconciliation_fkey",
            table,
            "account_reconciliations",
            ["account_reconciliation_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.create_index(
            f"idx_{table}_account_reconciliation_id",
            table,
            ["account_reconciliation_id"],
            postgresql_where=sa.text("account_reconciliation_id IS NOT NULL"),
        )

    # Keep updated_at current on UPDATE (the set_updated_at() function ships in the baseline schema).
    op.execute(
        "CREATE TRIGGER trg_account_reconciliations_updated_at BEFORE UPDATE ON account_reconciliations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )

    # Grant the restricted request role DML on the new table/sequence (0003's ALTER DEFAULT
    # PRIVILEGES should cover it, but grant explicitly to be safe).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON account_reconciliations TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE account_reconciliations_id_seq TO renly_app")

    # RLS: owned via user_id, same per-user policy shape as the other user-owned tables.
    op.execute("ALTER TABLE account_reconciliations ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY account_reconciliations_user_isolation ON account_reconciliations "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )


# Reverses the entry-side cascade links and the table (with its policy, trigger, and indexes). The two
# account_adjustment enum values stay: PostgreSQL cannot drop an enum value without recreating the type
# and rewriting every dependent column, and leaving them is harmless (same posture as 0009).
def downgrade() -> None:
    for table in _ENTRY_TABLES:
        op.drop_index(f"idx_{table}_account_reconciliation_id", table_name=table)
        op.drop_constraint(f"{table}_account_reconciliation_fkey", table, type_="foreignkey")
        op.drop_column(table, "account_reconciliation_id")

    op.execute("DROP POLICY IF EXISTS account_reconciliations_user_isolation ON account_reconciliations")
    op.execute("DROP TRIGGER IF EXISTS trg_account_reconciliations_updated_at ON account_reconciliations")
    op.drop_index("idx_account_reconciliations_account_date", table_name="account_reconciliations")
    op.drop_index("idx_account_reconciliations_user_id", table_name="account_reconciliations")
    op.drop_table("account_reconciliations")
