"""invite-only access: users.is_admin + invites table (admin invite gate)

Revision ID: 0006_invites_admin
Revises: 0005_refresh_tokens
Create Date: 2026-06-21

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006_invites_admin"
down_revision = "0005_refresh_tokens"
branch_labels = None
depends_on = None


# Adds the admin flag and the invites table for the invite-only access gate. is_admin gates the admin
# invite endpoints (multi-admin: flag each row); invites stores single-use, time-limited signup tokens
# (only the SHA-256 hash), locked behind a per-user RLS policy as defense-in-depth (the gate is
# is_admin at the endpoint + the privileged session every invite flow runs on).
def upgrade() -> None:
    # 1. users.is_admin — NOT NULL default false; existing rows become non-admins (promote the first
    #    admin directly with: UPDATE users SET is_admin = true WHERE email = '...').
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()))

    # 2. invites table (single-use, time-limited; stores only the SHA-256 hash of the raw token).
    invite_status = postgresql.ENUM("pending", "accepted", "revoked", name="invite_status")
    invite_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "invites",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("invited_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", postgresql.ENUM(name="invite_status", create_type=False), nullable=False, server_default="pending"),
        # Naive UTC (TIMESTAMP WITHOUT TIME ZONE): compared against naive utcnow() in the service.
        sa.Column("expires_at", sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=sa.text("(now() AT TIME ZONE 'utc')")),
    )
    op.create_index("idx_invites_invited_by", "invites", ["invited_by"])

    # 3. Grant the restricted request role DML on the new table/sequence. 0003's ALTER DEFAULT
    #    PRIVILEGES should cover objects the owner creates later, but grant explicitly to be safe.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON invites TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE invites_id_seq TO renly_app")

    # 4. RLS: owned via invited_by (the admin who created it), same per-user policy shape as the other
    #    user-owned tables. Every invite flow runs on the privileged session, so this is defense-in-depth.
    op.execute("ALTER TABLE invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY invites_admin_isolation ON invites "
        "USING (invited_by = app_current_user_id()) WITH CHECK (invited_by = app_current_user_id())"
    )


# Reverses the invites table + RLS and drops the users.is_admin column.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS invites_admin_isolation ON invites")
    op.drop_index("idx_invites_invited_by", table_name="invites")
    op.drop_table("invites")
    postgresql.ENUM(name="invite_status").drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "is_admin")
