"""cross-currency card settlement: what the funding account actually paid (account_amount)

Revision ID: 0016_settlement_account_amount
Revises: 0015_default_accounts
Create Date: 2026-08-17

"""

import sqlalchemy as sa
from alembic import op

revision = "0016_settlement_account_amount"
down_revision = "0015_default_accounts"
branch_labels = None
depends_on = None


# Adds the optional cash-leg amount to card_settlements. Nullable with no backfill: NULL means no
# conversion happened, so every existing row stays correct and the cash sums read
# coalesce(account_amount, amount). The two CHECKs mirror how transfers guards its own amount pair —
# a positive amount, and no cash amount without a cash leg to draw it from.
def upgrade() -> None:
    op.add_column("card_settlements", sa.Column("account_amount", sa.Numeric(18, 2), nullable=True))
    op.create_check_constraint(
        "card_settlements_positive_account_amount",
        "card_settlements",
        "account_amount IS NULL OR account_amount > 0",
    )
    op.create_check_constraint(
        "card_settlements_account_amount_needs_account",
        "card_settlements",
        "account_amount IS NULL OR account_id IS NOT NULL",
    )


# Drops the account_amount column and both CHECKs. Down-migrating discards what each cross-currency
# settlement drew from its account, so those rows revert to clearing the bucket with no cash leg
# recorded in the account's own currency.
def downgrade() -> None:
    op.drop_constraint("card_settlements_account_amount_needs_account", "card_settlements", type_="check")
    op.drop_constraint("card_settlements_positive_account_amount", "card_settlements", type_="check")
    op.drop_column("card_settlements", "account_amount")
