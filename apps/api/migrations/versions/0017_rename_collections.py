"""rename investment groups to collections (shared money, PR 1)

Revision ID: 0017_rename_collections
Revises: 0016_settlement_account_amount
Create Date: 2026-08-21

"""

from alembic import op

revision = "0017_rename_collections"
down_revision = "0016_settlement_account_amount"
branch_labels = None
depends_on = None


# Renames the investment-group concept to "collections" so the word `group` is free for the people
# entity the shared-money work introduces. Purely a rename: no column is added, dropped or retyped,
# and no row changes meaning. Every dependent object is renamed explicitly rather than left to follow
# the table, because Postgres renames NONE of them for you — a bare ALTER TABLE … RENAME leaves the
# sequence, the primary keys, the foreign keys and the CHECK still carrying their old auto-generated
# names, which would drift from what `database/01_create_tables.sql` builds on a fresh `db:init`.
# Policies and triggers DO follow the table (their stored parse trees resolve by OID), so only their
# names need renaming, not their bodies.
def upgrade() -> None:
    # Tables and the membership column.
    op.rename_table("investment_groups", "investment_collections")
    op.rename_table("investment_group_members", "investment_collection_members")
    op.alter_column("investment_collection_members", "group_id", new_column_name="collection_id")

    # The id sequence behind investment_collections.id. The column default resolves it by OID, so the
    # running database keeps working either way — but the NAME is still part of the schema contract a
    # fresh `db:init` produces, and any later migration that grants or alters this sequence by name
    # (as 0014 does for transfers) would look for the new one. Not cosmetic; do not drop this line.
    op.execute("ALTER SEQUENCE investment_groups_id_seq RENAME TO investment_collections_id_seq")

    # Auto-named constraints: two primary keys, three foreign keys, one CHECK.
    op.execute("ALTER TABLE investment_collections RENAME CONSTRAINT investment_groups_pkey TO investment_collections_pkey")
    op.execute("ALTER TABLE investment_collections RENAME CONSTRAINT investment_groups_user_id_fkey TO investment_collections_user_id_fkey")
    op.execute(
        "ALTER TABLE investment_collections RENAME CONSTRAINT investment_groups_target_percentage_check TO investment_collections_target_percentage_check"
    )
    op.execute("ALTER TABLE investment_collection_members RENAME CONSTRAINT investment_group_members_pkey TO investment_collection_members_pkey")
    op.execute(
        "ALTER TABLE investment_collection_members RENAME CONSTRAINT investment_group_members_investment_id_fkey TO investment_collection_members_investment_id_fkey"
    )
    op.execute(
        "ALTER TABLE investment_collection_members RENAME CONSTRAINT investment_group_members_group_id_fkey TO investment_collection_members_collection_id_fkey"
    )

    # Explicit indexes (the primary-key indexes were renamed with their constraints above).
    op.execute("ALTER INDEX idx_investment_groups_user_id RENAME TO idx_investment_collections_user_id")
    op.execute("ALTER INDEX idx_investment_group_members_group_id RENAME TO idx_investment_collection_members_collection_id")

    # Trigger and RLS policies — bodies are unchanged, only the names.
    op.execute("ALTER TRIGGER trg_investment_groups_updated_at ON investment_collections RENAME TO trg_investment_collections_updated_at")
    op.execute("ALTER POLICY investment_groups_user_isolation ON investment_collections RENAME TO investment_collections_user_isolation")
    op.execute("ALTER POLICY investment_group_members_isolation ON investment_collection_members RENAME TO investment_collection_members_isolation")

    # The two settings JSONB keys move with the concept. One statement per key, guarded on the key
    # being present, so a stored JSON null is carried across as a JSON null rather than collapsed
    # into an absent key (both read as "use the env default", but a pure rename should not decide
    # that for the row). Side effect worth knowing: user_settings has an updated_at trigger, so every
    # row that carried either key gets a fresh updated_at. That column is not exposed by any schema or
    # endpoint, so nothing user-facing changes.
    op.execute("UPDATE user_settings SET settings = (settings - 'max_groups') || jsonb_build_object('max_collections', settings -> 'max_groups') WHERE settings ? 'max_groups'")
    op.execute(
        "UPDATE user_settings SET settings = (settings - 'group_warning_pct') || jsonb_build_object('collection_warning_pct', settings -> 'group_warning_pct') WHERE settings ? 'group_warning_pct'"
    )


# Reverses every rename in the mirror order. Restoring the OLD table and column names is load-bearing,
# not tidiness: earlier migrations still refer to them (0003_rls drops its policy from
# `investment_group_members` by name), so a downgrade chain that ran past this one would fail against
# a table that no longer existed under that name.
def downgrade() -> None:
    op.execute(
        "UPDATE user_settings SET settings = (settings - 'collection_warning_pct') || jsonb_build_object('group_warning_pct', settings -> 'collection_warning_pct') WHERE settings ? 'collection_warning_pct'"
    )
    op.execute("UPDATE user_settings SET settings = (settings - 'max_collections') || jsonb_build_object('max_groups', settings -> 'max_collections') WHERE settings ? 'max_collections'")

    op.execute("ALTER POLICY investment_collection_members_isolation ON investment_collection_members RENAME TO investment_group_members_isolation")
    op.execute("ALTER POLICY investment_collections_user_isolation ON investment_collections RENAME TO investment_groups_user_isolation")
    op.execute("ALTER TRIGGER trg_investment_collections_updated_at ON investment_collections RENAME TO trg_investment_groups_updated_at")

    op.execute("ALTER INDEX idx_investment_collection_members_collection_id RENAME TO idx_investment_group_members_group_id")
    op.execute("ALTER INDEX idx_investment_collections_user_id RENAME TO idx_investment_groups_user_id")

    op.execute(
        "ALTER TABLE investment_collection_members RENAME CONSTRAINT investment_collection_members_collection_id_fkey TO investment_group_members_group_id_fkey"
    )
    op.execute(
        "ALTER TABLE investment_collection_members RENAME CONSTRAINT investment_collection_members_investment_id_fkey TO investment_group_members_investment_id_fkey"
    )
    op.execute("ALTER TABLE investment_collection_members RENAME CONSTRAINT investment_collection_members_pkey TO investment_group_members_pkey")
    op.execute(
        "ALTER TABLE investment_collections RENAME CONSTRAINT investment_collections_target_percentage_check TO investment_groups_target_percentage_check"
    )
    op.execute("ALTER TABLE investment_collections RENAME CONSTRAINT investment_collections_user_id_fkey TO investment_groups_user_id_fkey")
    op.execute("ALTER TABLE investment_collections RENAME CONSTRAINT investment_collections_pkey TO investment_groups_pkey")

    op.execute("ALTER SEQUENCE investment_collections_id_seq RENAME TO investment_groups_id_seq")

    op.alter_column("investment_collection_members", "collection_id", new_column_name="group_id")
    op.rename_table("investment_collection_members", "investment_group_members")
    op.rename_table("investment_collections", "investment_groups")
