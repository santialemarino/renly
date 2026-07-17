"""feedback: in-app feedback form storage (SHELL-7)

Revision ID: 0008_feedback
Revises: 0007_perf_indexes
Create Date: 2026-07-16

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_feedback"
down_revision = "0007_perf_indexes"
branch_labels = None
depends_on = None


# Adds the feedback table backing the in-app feedback form. Owned by user_id with the same per-user
# RLS policy as the other user-owned tables; the admin review list reads across users on the
# privileged session, and an email notification to admins is sent best-effort by the service.
def upgrade() -> None:
    feedback_category = postgresql.ENUM("bug", "idea", "question", "other", name="feedback_category")
    feedback_category.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "feedback",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", postgresql.ENUM(name="feedback_category", create_type=False), nullable=False),
        sa.Column("message", sa.String(length=2000), nullable=False),
        # Naive UTC (TIMESTAMP WITHOUT TIME ZONE) to match the app's naive utcnow().
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=sa.text("(now() AT TIME ZONE 'utc')")),
    )
    op.create_index("idx_feedback_user_id", "feedback", ["user_id"])

    # Grant the restricted request role DML on the new table/sequence (0003's ALTER DEFAULT
    # PRIVILEGES should cover it, but grant explicitly to be safe).
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON feedback TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE feedback_id_seq TO renly_app")

    # RLS: owned via user_id, same per-user policy shape as the other user-owned tables. The admin
    # review list reads on the privileged (owner) session, which is exempt from RLS.
    op.execute("ALTER TABLE feedback ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY feedback_user_isolation ON feedback "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )


# Reverses the feedback table + RLS policy + enum type.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS feedback_user_isolation ON feedback")
    op.drop_index("idx_feedback_user_id", table_name="feedback")
    op.drop_table("feedback")
    postgresql.ENUM(name="feedback_category").drop(op.get_bind(), checkfirst=True)
