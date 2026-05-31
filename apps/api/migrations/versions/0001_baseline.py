"""baseline (pre-launch schema; built from database/01_create_tables.sql)

Revision ID: 0001_baseline
Revises:
Create Date: 2026-05-31

"""

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


# Baseline anchor for Alembic adoption. The full pre-launch schema is built from
# apps/api/database/01_create_tables.sql (pnpm db:init applies it and stamps this revision).
# Existing databases are stamped here; forward changes ship as migrations below.
def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
