"""investment currencies: add BRL/EUR/GBP to the currency enum

Revision ID: 0009_investment_currencies
Revises: 0008_feedback
Create Date: 2026-07-18

"""

from alembic import op

revision = "0009_investment_currencies"
down_revision = "0008_feedback"
branch_labels = None
depends_on = None


# Adds BRL, EUR, and GBP to the `currency` enum so investments (and their snapshots/transactions)
# can be denominated in every currency Renly already supports for finance entries and conversion
# (all three already have USD exchange-rate pairs). The values append after the original ARS/USD,
# matching the fresh-build order in 01_create_tables.sql. IF NOT EXISTS keeps the migration idempotent.
def upgrade() -> None:
    op.execute("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'BRL'")
    op.execute("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'EUR'")
    op.execute("ALTER TYPE currency ADD VALUE IF NOT EXISTS 'GBP'")


# No-op: PostgreSQL cannot drop a value from an enum without recreating the type and rewriting every
# dependent column, and nothing requires removing them, so the downgrade intentionally does nothing.
def downgrade() -> None:
    pass
