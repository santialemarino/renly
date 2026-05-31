"""add user_plan enum and users.plan column

Revision ID: 0002_user_plan
Revises: 0001_baseline
Create Date: 2026-05-31

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002_user_plan"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


# Monetization seam: a user_plan enum (free/pro) and a NOT NULL users.plan column defaulting to free.
def upgrade() -> None:
    user_plan = postgresql.ENUM("free", "pro", name="user_plan")
    user_plan.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("plan", user_plan, nullable=False, server_default="free"))


def downgrade() -> None:
    op.drop_column("users", "plan")
    postgresql.ENUM(name="user_plan").drop(op.get_bind(), checkfirst=True)
