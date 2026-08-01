"""transfers: account-to-account movement (Bucket 3 #1, PR 5)

Revision ID: 0014_transfers
Revises: 0013_card_credit_category
Create Date: 2026-08-01

"""

import sqlalchemy as sa
from alembic import op

revision = "0014_transfers"
down_revision = "0013_card_credit_category"
branch_labels = None
depends_on = None


# Creates the transfers table: the one movement type that is neither income nor an expense, because
# net worth does not change — money leaves one owned account and arrives in another. Both amounts are
# stored so a cross-currency transfer (buy/sell USD) records the rate actually used; within one
# currency they are equal. Both account FKs cascade: deleting an account removes the movements that
# reference it, because a half-transfer would silently skew the surviving account's derived balance.
def upgrade() -> None:
    op.create_table(
        "transfers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("from_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("to_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        # A transfer to the same account is a no-op that would double-count in the balance union
        # (added on one side, subtracted on the other, but each leg is summed independently).
        sa.CheckConstraint("from_account_id <> to_account_id", name="transfers_distinct_accounts"),
        sa.CheckConstraint("from_amount > 0 AND to_amount > 0", name="transfers_positive_amounts"),
    )
    op.create_index("idx_transfers_user_id", "transfers", ["user_id"])
    # The balance union filters one leg at a time by account and bounds by date, so each leg gets its
    # own composite index rather than a bare FK index.
    op.create_index("idx_transfers_from_account_date", "transfers", ["from_account_id", "date"])
    op.create_index("idx_transfers_to_account_date", "transfers", ["to_account_id", "date"])

    # Keep updated_at current on UPDATE (the set_updated_at() function ships in the baseline schema).
    op.execute("CREATE TRIGGER trg_transfers_updated_at BEFORE UPDATE ON transfers FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    # Grant the restricted request role DML on the new table/sequence (0003's ALTER DEFAULT
    # PRIVILEGES should cover it, but grant explicitly to be safe).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON transfers TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE transfers_id_seq TO renly_app")

    # RLS: owned via user_id, same per-user policy shape as the other user-owned tables.
    op.execute("ALTER TABLE transfers ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY transfers_user_isolation ON transfers USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())")


# Drops the table with its policy, trigger, and indexes.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS transfers_user_isolation ON transfers")
    op.execute("DROP TRIGGER IF EXISTS trg_transfers_updated_at ON transfers")
    op.drop_index("idx_transfers_to_account_date", table_name="transfers")
    op.drop_index("idx_transfers_from_account_date", table_name="transfers")
    op.drop_index("idx_transfers_user_id", table_name="transfers")
    op.drop_table("transfers")
