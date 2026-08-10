"""default funding accounts: optional default_account_id on cards and recurring plans (conveniences batch)

Revision ID: 0015_default_accounts
Revises: 0014_transfers
Create Date: 2026-08-09

"""

import sqlalchemy as sa
from alembic import op

revision = "0015_default_accounts"
down_revision = "0014_transfers"
branch_labels = None
depends_on = None

# Tables gaining a nullable default_account_id FK to accounts(id). ON DELETE SET NULL: deleting an
# account clears the default rather than blocking the delete — a default is a convenience that
# pre-fills or links a FUTURE charge, never a record of money that already moved.
_TABLES = ("credit_cards", "subscriptions", "installments", "payment_obligations")


# Adds the optional default funding account to credit cards and the three recurring plan types,
# plus a partial index per table so deleting an account doesn't sequentially scan them.
def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("default_account_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(
            f"{table}_default_account_id_fkey",
            table,
            "accounts",
            ["default_account_id"],
            ["id"],
            ondelete="SET NULL",
        )
        op.create_index(
            f"idx_{table}_default_account_id",
            table,
            ["default_account_id"],
            postgresql_where=sa.text("default_account_id IS NOT NULL"),
        )


# Drops the default_account_id column (and its FK + index) from each table.
def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"idx_{table}_default_account_id", table_name=table)
        op.drop_constraint(f"{table}_default_account_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "default_account_id")
