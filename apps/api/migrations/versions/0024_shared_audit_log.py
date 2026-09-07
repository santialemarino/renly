"""shared audit log, plus the counterparty's delete on a re-agreement

Revision ID: 0024_shared_audit_log
Revises: 0023_notifications
Create Date: 2026-09-04

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0024_shared_audit_log"
down_revision = "0023_notifications"
branch_labels = None
depends_on = None

# Read and write are ONE policy here, unlike the shared-flow tables, and the reason is that this table
# has no second read branch to keep narrow: nothing about an audit entry has to stay visible to a
# former member, because an entry is a record of group activity rather than a movement in anybody's own
# account. So a single FOR ALL policy is correct, and Postgres's missing WITH CHECK for DELETE costs
# nothing — the USING clause already refuses a delete of a row the caller cannot see.
#
# The pot branch is the load-bearing half. An entry about a pot names it in `pot_id`, and
# app_can_view_pot is the SAME helper the pot tables use, so the trail can never state more than the
# pot page itself would. Entries with no pot are group-wide and stay visible to every member.
_POLICY = """
CREATE POLICY shared_audit_log_scope ON shared_audit_log
  USING (
    app_is_group_member(group_id)
    AND (pot_id IS NULL OR app_can_view_pot(pot_id))
  )
  WITH CHECK (
    app_is_group_member(group_id)
    AND (pot_id IS NULL OR app_can_view_pot(pot_id))
  )
"""

# The one policy this migration adds to a table it did not create, and it exists because a decision
# taken with the ownership ledger has a database half.
#
# `pot_ownership_events_scope_write` gates every command on app_can_write_pot, and write access is not
# granted by ownership: create_pot inserts can_write for the CREATOR only. So a co-owner whom a
# re-agreement moved units AWAY from cannot delete it — the service refuses first, but so would the
# database. The remedy needs both halves.
#
# FOR DELETE alone, and narrow in every other direction. It names no INSERT or UPDATE, so the
# counterparty gains no ability to record or rewrite anything (permissive policies are OR-ed per
# command, so the existing FOR ALL still governs those). It requires app_can_view_pot as well as the
# seat match, so a member the pot is hidden from cannot reach a row they cannot read. And it is
# restricted to `reagreement`: a contribution or a withdrawal moves the mover's own money and an
# opening is the division everyone agreed to, so neither has a counterparty with a claim to undo it.
_COUNTERPARTY_DELETE = """
CREATE POLICY pot_ownership_events_counterparty_delete ON pot_ownership_events FOR DELETE
  USING (
    pot_ownership_events.type = 'reagreement'
    AND app_can_view_pot(pot_ownership_events.pot_id)
    AND EXISTS (
      SELECT 1 FROM group_members gm
      WHERE gm.id IN (pot_ownership_events.member_id, pot_ownership_events.counterparty_member_id)
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
    )
  )
"""


# Creates the audit trail for shared entities.
#
# Three column choices are decisions rather than defaults, and each is stated in the model too:
#
#   * entity_type and action are VARCHAR, not Postgres enums — the only string enums in this schema
#     that are. The audit log is the last piece of the membership kernel that had to stay
#     entity-agnostic, so a second module over the same groups adds an entity type in Python and needs
#     no migration at all. Nothing outside this API ever supplies either value.
#
#   * entity_id and pot_id carry NO foreign key. entity_id names a row in one of nine tables, which no
#     single FK could express; pot_id omits one so an entry OUTLIVES the pot it describes — a CASCADE
#     would delete a pot's whole history at the exact moment somebody deleted the pot. Since
#     app_can_view_pot answers false for a pot that is gone, those entries go dark rather than becoming
#     group-visible, which is the fail-closed direction.
#
#   * group_id DOES cascade. A deleted group takes its trail with it, and losing nothing readable in
#     the process: app_is_group_member is false for a group that no longer exists, so every entry would
#     already be invisible to everyone.
#
# There is no updated_at and no trigger: an entry is an immutable record of something that happened.
# What makes it immutable is the GRANT below rather than a trigger — see the comment there.
def upgrade() -> None:
    op.create_table(
        "shared_audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        # SET NULL rather than CASCADE, exactly as created_by is on every other table: deleting an
        # account must not erase the record of what that account did to money other people share.
        sa.Column("actor_user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("pot_id", sa.BigInteger(), nullable=True),
        # The values the copy interpolates. JSONB rather than columns precisely because the layer must
        # not know what a pot or an expense is: every action carries its own shape.
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    # The only way this table is ever read: one group's entries, newest first. created_at DESC leads
    # because that is the sort, and id DESC breaks the tie so two entries written in the same
    # transaction — an opening writes one and its notification-worthy siblings may too — come back in a
    # stable order rather than an arbitrary one.
    op.create_index("idx_shared_audit_log_group_created", "shared_audit_log", ["group_id", sa.text("created_at DESC"), sa.text("id DESC")])

    # APPEND-ONLY, and this is the grant rather than a trigger. 0003's ALTER DEFAULT PRIVILEGES hands
    # renly_app all four verbs on every new table, so UPDATE and DELETE are revoked back off explicitly
    # — an audit entry the request role can rewrite or erase is not an audit entry. A BEFORE UPDATE OR
    # DELETE trigger would have been the other way to say it and is the wrong one: an FK cascade
    # performs a real DELETE on the child, so a raising trigger would make deleting a group impossible.
    # The two cascades this table has (group_id, actor_user_id) run as the referencing table's OWNER
    # and are exempt from both the grant and the policy, which is what lets them still work.
    op.execute("GRANT SELECT, INSERT ON shared_audit_log TO renly_app")
    op.execute("REVOKE UPDATE, DELETE ON shared_audit_log FROM renly_app")
    op.execute("GRANT USAGE, SELECT ON SEQUENCE shared_audit_log_id_seq TO renly_app")
    op.execute("ALTER TABLE shared_audit_log ENABLE ROW LEVEL SECURITY")
    op.execute(_POLICY)
    op.execute(_COUNTERPARTY_DELETE)


# Drops the audit trail entirely, and takes the counterparty's delete back off the ownership ledger.
# Down-migrating discards every recorded act; no figure in the app is derived from one, and no column
# was added anywhere else, so every balance reads exactly as it did.
def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_counterparty_delete ON pot_ownership_events")
    op.drop_table("shared_audit_log")
