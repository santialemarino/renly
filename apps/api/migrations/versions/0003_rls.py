"""row-level security: denormalized user_id on child tables + per-user RLS policies (SEC-15)

Revision ID: 0003_rls
Revises: 0002_user_plan
Create Date: 2026-06-07

"""

import sqlalchemy as sa
from alembic import op

revision = "0003_rls"
down_revision = "0002_user_plan"
branch_labels = None
depends_on = None

# Tables isolated by a direct user_id column (identical owner-match policy on each).
_USER_ID_TABLES = (
    "investments",
    "investment_snapshots",
    "transactions",
    "investment_groups",
    "credit_cards",
    "income_entries",
    "card_settlements",
    "subscriptions",
    "installments",
    "expense_entries",
    "card_reconciliations",
    "payment_obligations",
    "api_keys",
    "user_settings",
)

# Child tables gaining a denormalized user_id, with the parent join used to backfill it.
_DENORMALIZED = (
    ("investment_snapshots", "investments", "investment_id"),
    ("transactions", "investments", "investment_id"),
    ("card_settlements", "credit_cards", "credit_card_id"),
)


# Adds the denormalized user_id to the hot child tables, then locks every user-owned table behind
# a row-level-security policy keyed on the per-request app.current_user_id GUC, served by a
# restricted role that (unlike the owner) does not bypass RLS.
def upgrade() -> None:
    # 1. Denormalize user_id onto the child tables: add nullable, backfill from the parent, then
    #    enforce NOT NULL + FK + index.
    for table, parent, fk_col in _DENORMALIZED:
        op.add_column(table, sa.Column("user_id", sa.BigInteger(), nullable=True))
        op.execute(f"UPDATE {table} c SET user_id = p.user_id FROM {parent} p WHERE c.{fk_col} = p.id")
        op.alter_column(table, "user_id", nullable=False)
        op.create_foreign_key(f"{table}_user_id_fkey", table, "users", ["user_id"], ["id"], ondelete="CASCADE")
        op.create_index(f"idx_{'snapshots' if table == 'investment_snapshots' else table}_user_id", table, ["user_id"])

    # 2. Helper resolving the current user id from the per-transaction GUC; NULL (no rows) when unset.
    op.execute(
        "CREATE OR REPLACE FUNCTION app_current_user_id() RETURNS BIGINT "
        "LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting('app.current_user_id', true), '')::bigint $$"
    )

    # 3. Restricted request role (cluster-global; guard for shared clusters). Local-dev password;
    #    production provisions it with a real secret.
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'renly_app') THEN "
        "CREATE ROLE renly_app LOGIN PASSWORD 'renly_app' NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; "
        "END IF; END $$"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO renly_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO renly_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO renly_app")
    op.execute("GRANT EXECUTE ON FUNCTION app_current_user_id() TO renly_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO renly_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO renly_app")

    # 4. users keys on its own id; every other user-owned table keys on user_id.
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY users_self_isolation ON users USING (id = app_current_user_id()) WITH CHECK (id = app_current_user_id())")
    for table in _USER_ID_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY {table}_user_isolation ON {table} "
            "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
        )

    # 5. investment_group_members is a pure junction — isolate via an EXISTS-join to the parent
    #    investment (both parents share one owner per the SEC-4 FK checks).
    op.execute("ALTER TABLE investment_group_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY investment_group_members_isolation ON investment_group_members "
        "USING (EXISTS (SELECT 1 FROM investments i WHERE i.id = investment_group_members.investment_id "
        "AND i.user_id = app_current_user_id())) "
        "WITH CHECK (EXISTS (SELECT 1 FROM investments i WHERE i.id = investment_group_members.investment_id "
        "AND i.user_id = app_current_user_id()))"
    )


# Reverses the RLS lockdown and the child-table denormalization. Leaves the renly_app role in place
# (it is cluster-global and may own privileges in other databases); revoke/drop it manually if needed.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS investment_group_members_isolation ON investment_group_members")
    op.execute("ALTER TABLE investment_group_members DISABLE ROW LEVEL SECURITY")
    for table in _USER_ID_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_user_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS users_self_isolation ON users")
    op.execute("ALTER TABLE users DISABLE ROW LEVEL SECURITY")

    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM renly_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE, SELECT ON SEQUENCES FROM renly_app")
    op.execute("REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM renly_app")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM renly_app")
    op.execute("REVOKE ALL ON SCHEMA public FROM renly_app")
    op.execute("DROP FUNCTION IF EXISTS app_current_user_id()")

    for table, _parent, _fk_col in _DENORMALIZED:
        op.drop_index(f"idx_{'snapshots' if table == 'investment_snapshots' else table}_user_id", table_name=table)
        op.drop_constraint(f"{table}_user_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "user_id")
