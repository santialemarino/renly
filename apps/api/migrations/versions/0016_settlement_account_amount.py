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
# coalesce(account_amount, amount).
#
# Only ONE CHECK, deliberately. The obvious second one — "account_amount IS NULL OR account_id IS NOT
# NULL" — is unsound here and was measured to be: account_id is ON DELETE SET NULL, which Postgres
# performs as `UPDATE card_settlements SET account_id = NULL`, so that CHECK makes any account that ever
# funded a cross-currency settlement PERMANENTLY undeletable (a generic integrity 409). Unlinking on
# delete is the documented, wanted behaviour — history is preserved, never cascade-deleted — so the
# constraint would forbid a legitimate operation. Transfers avoids the whole class only because its legs
# are NOT NULL + ON DELETE CASCADE, which is why its guard does not carry over. The rule still holds
# where it can be enforced without breaking the unlink: the service refuses it on write
# (SettlementAccountAmountWithoutAccountError) and clears account_amount when it drops the account link.
def upgrade() -> None:
    op.add_column("card_settlements", sa.Column("account_amount", sa.Numeric(18, 2), nullable=True))
    op.create_check_constraint(
        "card_settlements_positive_account_amount",
        "card_settlements",
        "account_amount IS NULL OR account_amount > 0",
    )


# Drops the account_amount column and its CHECK. Down-migrating discards what each cross-currency
# settlement drew from its account, so those rows revert to clearing the bucket with no cash leg
# recorded in the account's own currency.
def downgrade() -> None:
    op.drop_constraint("card_settlements_positive_account_amount", "card_settlements", type_="check")
    op.drop_column("card_settlements", "account_amount")
