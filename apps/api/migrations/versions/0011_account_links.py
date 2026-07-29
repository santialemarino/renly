"""account links: optional account_id on expenses / income / settlements (Bucket 3 #1, PR 2)

Revision ID: 0011_account_links
Revises: 0010_accounts
Create Date: 2026-07-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0011_account_links"
down_revision = "0010_accounts"
branch_labels = None
depends_on = None

# Tables gaining a nullable account_id FK to accounts(id). ON DELETE SET NULL: deleting an account
# un-attributes its linked entries (their history is preserved), never cascades the entry away.
_TABLES = ("expense_entries", "income_entries", "card_settlements")


# Adds the optional money-link to the cash/bank account entity: a nullable account_id on each money
# table, plus a partial index for the balance-derivation sum queries (only linked rows matter).
def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("account_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(f"{table}_account_id_fkey", table, "accounts", ["account_id"], ["id"], ondelete="SET NULL")
        op.create_index(
            f"idx_{table}_account_id",
            table,
            ["account_id"],
            postgresql_where=sa.text("account_id IS NOT NULL"),
        )


# Drops the account_id column (and its FK + index) from each money table.
def downgrade() -> None:
    for table in _TABLES:
        op.drop_index(f"idx_{table}_account_id", table_name=table)
        op.drop_constraint(f"{table}_account_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "account_id")
