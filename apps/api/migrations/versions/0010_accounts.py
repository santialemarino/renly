"""accounts: cash / bank account entity (Deferred Bucket 3 #1, PR 1)

Revision ID: 0010_accounts
Revises: 0009_investment_currencies
Create Date: 2026-07-20

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010_accounts"
down_revision = "0009_investment_currencies"
branch_labels = None
depends_on = None


# Adds the accounts table backing the cash/bank account entity. Owned by user_id with the same
# per-user RLS policy as the other user-owned tables. The running balance is derived at query time
# (opening_balance in this PR; extended with linked movements later) — no stored balance column.
def upgrade() -> None:
    account_type = postgresql.ENUM("cash", "bank", "wallet", "other", name="account_type")
    account_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "accounts",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("type", postgresql.ENUM(name="account_type", create_type=False), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("opening_balance", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("opening_date", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_accounts_user_id", "accounts", ["user_id"])
    op.create_index("idx_accounts_user_active", "accounts", ["user_id", "is_active"])

    # Keep updated_at current on UPDATE (the set_updated_at() function ships in the baseline schema).
    op.execute("CREATE TRIGGER trg_accounts_updated_at BEFORE UPDATE ON accounts FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    # Grant the restricted request role DML on the new table/sequence (0003's ALTER DEFAULT
    # PRIVILEGES should cover it, but grant explicitly to be safe).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON accounts TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE accounts_id_seq TO renly_app")

    # RLS: owned via user_id, same per-user policy shape as the other user-owned tables.
    op.execute("ALTER TABLE accounts ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY accounts_user_isolation ON accounts "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )


# Reverses the accounts table + RLS policy + trigger + enum type.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS accounts_user_isolation ON accounts")
    op.execute("DROP TRIGGER IF EXISTS trg_accounts_updated_at ON accounts")
    op.drop_index("idx_accounts_user_active", table_name="accounts")
    op.drop_index("idx_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
    postgresql.ENUM(name="account_type").drop(op.get_bind(), checkfirst=True)
