"""account lifecycle: users.email_verified_at + auth_tokens table (AUTH-1/2/8)

Revision ID: 0004_account_lifecycle
Revises: 0003_rls
Create Date: 2026-06-20

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004_account_lifecycle"
down_revision = "0003_rls"
branch_labels = None
depends_on = None


# Adds the email-verification column (grandfathering existing accounts as verified so live users
# aren't locked out) and the single-use auth_tokens table for verification / reset / email change,
# locked behind the same per-user RLS policy as every other user-owned table (SEC-15).
def upgrade() -> None:
    # 1. users.email_verified_at — nullable; backfill existing rows as verified so the new login
    #    gate (AUTH-1) doesn't lock out accounts created before email verification existed.
    op.add_column("users", sa.Column("email_verified_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.execute("UPDATE users SET email_verified_at = NOW() WHERE email_verified_at IS NULL")

    # 2. auth_tokens table (single-use, time-limited; stores only the SHA-256 hash of the raw token).
    auth_token_type = postgresql.ENUM(
        "email_verification", "password_reset", "email_change", name="auth_token_type"
    )
    auth_token_type.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("token_type", postgresql.ENUM(name="auth_token_type", create_type=False), nullable=False),
        sa.Column("new_email", sa.String(length=255), nullable=True),
        # Naive UTC (TIMESTAMP WITHOUT TIME ZONE): compared against naive utcnow() in the service.
        sa.Column("expires_at", sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=sa.text("(now() AT TIME ZONE 'utc')")),
    )
    op.create_index("idx_auth_tokens_user_id", "auth_tokens", ["user_id"])
    op.create_index("idx_auth_tokens_user_type", "auth_tokens", ["user_id", "token_type"])

    # 3. Grant the restricted request role DML on the new table/sequence. 0003's ALTER DEFAULT
    #    PRIVILEGES should cover objects the owner creates later, but grant explicitly to be safe.
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON auth_tokens TO renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE auth_tokens_id_seq TO renly_app")

    # 4. RLS: owned via user_id, same per-user policy as the other user-owned tables.
    op.execute("ALTER TABLE auth_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY auth_tokens_user_isolation ON auth_tokens "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )


# Reverses the auth_tokens table + RLS and drops the email-verification column.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS auth_tokens_user_isolation ON auth_tokens")
    op.drop_index("idx_auth_tokens_user_type", table_name="auth_tokens")
    op.drop_index("idx_auth_tokens_user_id", table_name="auth_tokens")
    op.drop_table("auth_tokens")
    postgresql.ENUM(name="auth_token_type").drop(op.get_bind(), checkfirst=True)
    op.drop_column("users", "email_verified_at")
