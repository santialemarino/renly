"""card credits: expense-side category so a card credit can reduce the bucket

Revision ID: 0013_card_credit_category
Revises: 0012_account_reconciliations
Create Date: 2026-07-29

"""

from alembic import op

revision = "0013_card_credit_category"
down_revision = "0012_account_reconciliations"
branch_labels = None
depends_on = None


# A credit-card bucket balance is `sum(expenses) - sum(settlements)`, so an income row can never
# reduce it — which meant a reconciliation whose statement came in BELOW the computed balance posted
# an income and left the card overstated. The adjustment is now always a card-linked expense signed
# by direction (positive = the bank charged more, negative = a credit), and a negative one needs its
# own category so a credit is not mislabelled as a fee.
#
# `income_category.card_credits_and_refunds` stays declared: PostgreSQL cannot drop an enum value
# without recreating the type, and it is harmless (no rows ever used it — the credit path had never
# fired before this fix).
def upgrade() -> None:
    # BEFORE 'account_adjustment' keeps the two card values adjacent and 'other' last, matching the
    # fresh-build enum order in 01_create_tables.sql. IF NOT EXISTS keeps the migration idempotent.
    op.execute("ALTER TYPE expense_category ADD VALUE IF NOT EXISTS 'card_credits_and_refunds' BEFORE 'account_adjustment'")


# No-op: PostgreSQL cannot drop a value from an enum without recreating the type and rewriting every
# dependent column, and nothing requires removing it (same posture as 0009 and 0012).
def downgrade() -> None:
    pass
