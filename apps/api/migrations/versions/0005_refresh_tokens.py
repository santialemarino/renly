"""refresh tokens: rotating refresh-token table for silent access-token renewal (AUTH-7)

Revision ID: 0005_refresh_tokens
Revises: 0004_account_lifecycle
Create Date: 2026-06-20

"""

import sqlalchemy as sa
from alembic import op

revision = "0005_refresh_tokens"
down_revision = "0004_account_lifecycle"
branch_labels = None
depends_on = None


# Adds the refresh_tokens table (rotating, single-use; stores only the SHA-256 hash of the raw
# token), locked behind the same per-user RLS policy as every other user-owned table (SEC-15).
def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("family_id", sa.String(length=32), nullable=False),
        sa.Column("session_epoch", sa.BigInteger(), nullable=False),
        sa.Column("remember_me", sa.Boolean(), nullable=False),
        # Naive UTC (TIMESTAMP WITHOUT TIME ZONE): compared against naive utcnow() in the service.
        sa.Column("expires_at", sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=sa.text("(now() AT TIME ZONE 'utc')")),
    )
    op.create_index("idx_refresh_tokens_user_id", "refresh_tokens", ["user_id"])
    op.create_index("idx_refresh_tokens_family", "refresh_tokens", ["family_id"])

    # Grant the restricted request role DML on the new table/sequence. 0003's ALTER DEFAULT
    # PRIVILEGES should cover objects the owner creates later, but grant explicitly to be safe.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON refresh_tokens TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE refresh_tokens_id_seq TO renly_app")

    # RLS: owned via user_id, same per-user policy as the other user-owned tables.
    op.execute("ALTER TABLE refresh_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY refresh_tokens_user_isolation ON refresh_tokens "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )


# Reverses the refresh_tokens table + RLS.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS refresh_tokens_user_isolation ON refresh_tokens")
    op.drop_index("idx_refresh_tokens_family", table_name="refresh_tokens")
    op.drop_index("idx_refresh_tokens_user_id", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
