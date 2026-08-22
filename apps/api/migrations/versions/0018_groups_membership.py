"""groups, membership and group invites — the shared-money people entity

Revision ID: 0018_groups_membership
Revises: 0017_rename_collections
Create Date: 2026-08-22

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_groups_membership"
down_revision = "0017_rename_collections"
branch_labels = None
depends_on = None

# Kept byte-identical to the copy in database/01_create_tables.sql, indentation included: pg_dump
# reproduces a function body verbatim, so differently-indented copies make a migrated database and a
# fresh one differ textually even though they behave the same. Hence the unindented literal.
_APP_IS_GROUP_MEMBER_SQL = """
CREATE OR REPLACE FUNCTION app_is_group_member(p_group_id BIGINT) RETURNS BOOLEAN
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    SELECT EXISTS (
      SELECT 1 FROM group_members gm
      WHERE gm.group_id = p_group_id
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
    )
  $$
"""


# Adds the people entity behind shared money: a group, its member seats, and a single-use invite per
# seat. Nothing money-specific lands here — `groups` carries who the people are and nothing about what
# they share, so the same membership kernel is reusable by a non-money module unchanged.
#
# This migration introduces the FIRST non-owner-match RLS policy shape in the schema. Every existing
# policy compares a row's user_id to app_current_user_id(); a group's rows belong to the group, so the
# predicate asks "is the requesting user an active member" through app_is_group_member() — one
# SECURITY DEFINER helper rather than a predicate copy-pasted per table. The helper is not a
# preference: a policy ON group_members that sub-queried group_members is evaluated recursively and
# Postgres aborts it with "infinite recursion detected in policy for relation".
def upgrade() -> None:
    group_kind = postgresql.ENUM("household", "couple", "trip", "flat", "other", name="group_kind")
    group_kind.create(op.get_bind(), checkfirst=True)
    group_member_role = postgresql.ENUM("admin", "member", name="group_member_role")
    group_member_role.create(op.get_bind(), checkfirst=True)

    # created_by is authorship, not ownership — a group has no single owner. ON DELETE SET NULL because
    # the group belongs to its members: deleting the creator's account must not delete a group other
    # people are still using (every other users FK in this schema CASCADEs precisely because those
    # tables are single-owner, which this one is not).
    op.create_table(
        "groups",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", postgresql.ENUM(name="group_kind", create_type=False), nullable=False),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_groups_created_by", "groups", ["created_by"])

    # One row per seat. user_id NULL is a name-only placeholder — someone tracked in the group who has
    # no Renly account; accepting an invite fills it in, which is the whole "placeholder upgrades on
    # join" mechanic (no migration, no recompute — the seat's history is already attached to this row).
    # Removing a member DEACTIVATES the seat rather than deleting it, so rows that will later reference
    # it (splits, settlements, ownership units) keep a real counterparty; is_active is inside the RLS
    # predicate, so deactivating revokes access in the same statement that removes the person.
    op.create_table(
        "group_members",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", postgresql.ENUM(name="group_member_role", create_type=False), nullable=False, server_default="member"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("joined_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_group_members_group_id", "group_members", ["group_id"])
    # Every membership check resolves "which groups is this user in", so the lookup is by user_id with
    # group_id and is_active covered; the partial predicate skips every placeholder row.
    op.create_index(
        "idx_group_members_user_active",
        "group_members",
        ["user_id", "group_id", "is_active"],
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )
    # One seat per account per group. Partial because placeholders all have user_id NULL, which a plain
    # UNIQUE would not constrain but would also not usefully index.
    op.create_index(
        "idx_group_members_group_user",
        "group_members",
        ["group_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("user_id IS NOT NULL"),
    )

    # Same proven mechanism as `invites` (high-entropy raw token, only its SHA-256 hash stored,
    # time-limited, single-use via consumed_at, rotate-on-resend) in a deliberately SEPARATE table:
    # `invites` has a GLOBAL UNIQUE (email) because it gates platform signup ("one active invite per
    # email"), while the same person may legitimately hold seats in several groups at once — and a
    # group invite must never grant signup access, nor consuming one consume the other.
    # The token is the credential: no account is created here, it only links an existing account to
    # this seat, which is also what makes a shareable link possible. email is informational (the
    # address the link was sent to; NULL for a link-only invite). Timestamps are naive UTC to match
    # `invites` and the service's utcnow() comparisons. No updated_at, also matching `invites`:
    # rotation restarts expires_at in place, and set_updated_at() writes NOW() (timestamptz), which
    # would land in the session timezone on a naive column.
    op.create_table(
        "group_invites",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=False), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=False), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=False), nullable=False, server_default=sa.text("(now() AT TIME ZONE 'utc')")),
    )
    op.create_index("idx_group_invites_group_id", "group_invites", ["group_id"])

    for table in ("groups", "group_members"):
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION set_updated_at()")

    # Grant the restricted request role DML on the new tables/sequences (0003's ALTER DEFAULT
    # PRIVILEGES should cover them, but grant explicitly to be safe — a lost GRANT is invisible to a
    # pg_dump comparison run with --no-privileges).
    for table in ("groups", "group_members", "group_invites"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO renly_app")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO renly_app")

    # SECURITY DEFINER so the body runs as the table owner, which is exempt from RLS — that is what
    # terminates the lookup instead of recursing. It leaks nothing: it takes a group id and returns a
    # boolean about the CALLING user's own membership, which the caller necessarily already knows, for
    # any argument. search_path is pinned so a caller cannot shadow group_members with a temp table.
    # The default PUBLIC EXECUTE grant every function receives is revoked first, because this one runs
    # as the owner (app_current_user_id() keeps the default — it is not SECURITY DEFINER).
    op.execute(_APP_IS_GROUP_MEMBER_SQL)
    op.execute("REVOKE ALL ON FUNCTION app_is_group_member(BIGINT) FROM PUBLIC")
    op.execute("GRANT EXECUTE ON FUNCTION app_is_group_member(BIGINT) TO renly_app")

    # `role` appears nowhere in the predicate: group administration is management, not access, so an
    # admin sees precisely what any member sees. group_members is keyed through the GROUP rather than
    # its own user_id, because a member must see every seat in their group — including the name-only
    # placeholders, which have no user_id to match on at all.
    op.execute("ALTER TABLE groups ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY groups_member_isolation ON groups USING (app_is_group_member(id)) WITH CHECK (app_is_group_member(id))")
    op.execute("ALTER TABLE group_members ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY group_members_member_isolation ON group_members "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )
    op.execute("ALTER TABLE group_invites ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY group_invites_member_isolation ON group_invites "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )


# Reverses everything upgrade() created, innermost first: policies, the membership helper, the
# triggers, then the tables (whose indexes and grants go with them) and finally the two enum types.
# The helper is dropped explicitly rather than left behind — a later re-upgrade uses CREATE OR REPLACE,
# but leaving a SECURITY DEFINER function granted to renly_app after its tables are gone would be a
# stray privilege on an object nothing describes.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS group_invites_member_isolation ON group_invites")
    op.execute("DROP POLICY IF EXISTS group_members_member_isolation ON group_members")
    op.execute("DROP POLICY IF EXISTS groups_member_isolation ON groups")
    op.execute("DROP FUNCTION IF EXISTS app_is_group_member(BIGINT)")

    for table in ("groups", "group_members"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")

    op.drop_index("idx_group_invites_group_id", table_name="group_invites")
    op.drop_table("group_invites")
    op.drop_index("idx_group_members_group_user", table_name="group_members")
    op.drop_index("idx_group_members_user_active", table_name="group_members")
    op.drop_index("idx_group_members_group_id", table_name="group_members")
    op.drop_table("group_members")
    op.drop_index("idx_groups_created_by", table_name="groups")
    op.drop_table("groups")

    postgresql.ENUM(name="group_member_role").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="group_kind").drop(op.get_bind(), checkfirst=True)
