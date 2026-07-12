"""perf: composite exchange_rates (pair, date) index for per-pair date-ordered scans

Revision ID: 0007_perf_indexes
Revises: 0006_invites_admin
Create Date: 2026-07-12

"""

from alembic import op

revision = "0007_perf_indexes"
down_revision = "0006_invites_admin"
branch_labels = None
depends_on = None


# The RateLookup load and per-pair latest-rate queries filter and order by (pair, date); the
# existing idx_exchange_rates_date (date DESC) cannot serve a per-pair scan.
def upgrade() -> None:
    op.create_index("idx_exchange_rates_pair_date", "exchange_rates", ["pair", "date"])


def downgrade() -> None:
    op.drop_index("idx_exchange_rates_pair_date", table_name="exchange_rates")
