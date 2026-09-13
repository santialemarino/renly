"""a re-agreement's confirmation, and the lock it puts on the entry

Revision ID: 0025_reagreement_confirm
Revises: 0024_shared_audit_log
Create Date: 2026-09-08

"""

import sqlalchemy as sa
from alembic import op

revision = "0025_reagreement_confirm"
down_revision = "0024_shared_audit_log"
branch_labels = None
depends_on = None

# ▸ `caller.is_active` is REDUNDANT today and kept deliberately. What enforces it is one layer down:
# this EXISTS runs as the invoking role rather than in a SECURITY DEFINER body, so group_members' own
# policy (app_is_group_member(), which requires an ACTIVE seat) applies inside it, and the UNIQUE index
# on (group_id, user_id) means the caller has at most one seat per group. Proven on a row naming a
# user's INACTIVE seat in ANOTHER group — nothing ties an event's member_id to the pot's group —
# where app_can_view_pot returns TRUE and the update is refused either way. Kept because that
# redundancy rests on three artifacts in three places, and wrapping this EXISTS in a SECURITY DEFINER
# helper would silently remove the first of them. No test can reach it.
#
# The affected seat, as one expression rather than a set of two seats — which is what makes the answer
# always be somebody who did NOT record the row, including a third party with write access recording a
# change between two other members. The giver, unless the giver recorded it, in which case the receiver.
#
# `giver.user_id = created_by` is a plain equality on purpose: a NULL on either side (a name-only giver,
# or a recorder whose account has since been deleted) yields NULL, falls to the ELSE, and leaves the
# answer on the giver — the seat with something taken, and so the safe direction to fail in.
_AFFECTED_SEAT = """
    pot_ownership_events.type = 'reagreement'
    AND app_can_view_pot(pot_ownership_events.pot_id)
    AND EXISTS (
      SELECT 1 FROM group_members giver
      JOIN group_members caller
        ON caller.id = CASE WHEN giver.user_id = pot_ownership_events.created_by
                            THEN pot_ownership_events.counterparty_member_id
                            ELSE pot_ownership_events.member_id
                       END
      WHERE giver.id = pot_ownership_events.member_id
        AND caller.user_id = app_current_user_id()
        AND caller.is_active
    )
"""

# The only UPDATE the database permits on this table at all. Stated in SQL as well as in Python because
# the whole decision is that pot WRITE access is not the trust boundary: create_pot grants can_write to
# the creator only, so a rule keyed on it would let whoever recorded the change also vouch for it.
#
# No WITH CHECK, and that is not an omission: Postgres reuses the USING expression as the check when one
# is absent, so the row has to qualify both before and after either way — and the column grant below
# leaves nothing the predicate reads writable, so the two could never have differed.
_CONFIRM_UPDATE = f"""
CREATE POLICY pot_ownership_events_confirm_update ON pot_ownership_events FOR UPDATE
  USING ({_AFFECTED_SEAT})
"""

# The FOR ALL this replaces governed SELECT, INSERT, UPDATE and DELETE on one predicate. Splitting it
# drops UPDATE from write access, which nothing in the app ever needed: a ledger entry is inserted and
# deleted, never edited, and a row whose units a writer could rewrite after the fact would make every
# derived balance a claim about the present rather than a replay of what happened.
#
# The delete carries the LOCK, and it is what makes confirming more than a label: a confirmed entry is
# undeletable by everybody, a pot's own writer included. A no-op for the other three event types, which
# the CHECK below keeps unconfirmable. FK cascades from pots and group_members run as this table's owner
# and are exempt, so deleting a pot still takes its confirmed entries with it.
_SCOPE_WRITE_SPLIT = (
    "CREATE POLICY pot_ownership_events_scope_insert ON pot_ownership_events FOR INSERT WITH CHECK (app_can_write_pot(pot_id))",
    "CREATE POLICY pot_ownership_events_scope_delete ON pot_ownership_events FOR DELETE"
    " USING (app_can_write_pot(pot_id) AND confirmed_at IS NULL)",
)

# PR 10's remedy, re-created with the lock in it. A named seat's delete is what they have BEFORE they
# agree, and agreeing is what gives it up — so the policy has to stop at the confirmation exactly as the
# writer's does, or the database would permit the one deletion the service refuses.
_COUNTERPARTY_DELETE = """
CREATE POLICY pot_ownership_events_counterparty_delete ON pot_ownership_events FOR DELETE
  USING (
    pot_ownership_events.type = 'reagreement'
    AND pot_ownership_events.confirmed_at IS NULL
    AND app_can_view_pot(pot_ownership_events.pot_id)
    AND EXISTS (
      SELECT 1 FROM group_members gm
      WHERE gm.id IN (pot_ownership_events.member_id, pot_ownership_events.counterparty_member_id)
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
    )
  )
"""


# Adds confirmed_at to the ownership ledger and the access rules that make it a lock.
#
# Nothing is backfilled and nothing needs to be: NULL is "unconfirmed", which is what every existing
# entry is and what the surface already showed. No balance moves — a re-agreement counted from the
# moment it was recorded before this migration and still does, which is the whole reason the column is
# a lock rather than a gate.
def upgrade() -> None:
    op.add_column("pot_ownership_events", sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True))
    # Only a reagreement is confirmed, for the same reason only a reagreement may be deleted by a named
    # seat: it is the only event type that moves value between two people with no money changing hands.
    op.create_check_constraint(
        "pot_ownership_events_confirmable",
        "pot_ownership_events",
        "confirmed_at IS NULL OR type = 'reagreement'",
    )

    op.execute("DROP POLICY IF EXISTS pot_ownership_events_scope_write ON pot_ownership_events")
    for statement in _SCOPE_WRITE_SPLIT:
        op.execute(statement)
    op.execute(_CONFIRM_UPDATE)
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_counterparty_delete ON pot_ownership_events")
    op.execute(_COUNTERPARTY_DELETE)

    # UPDATE narrowed to the confirmation's own column. 0003's ALTER DEFAULT PRIVILEGES hands renly_app
    # all four verbs, so the table-level UPDATE is revoked and handed back per column — a policy cannot
    # express this, since RLS filters rows and never columns. confirmed_at alone, not updated_at with
    # it: column privileges are checked against a statement's SET list, and nothing in this codebase
    # ever sets updated_at itself — the BEFORE UPDATE trigger writes NEW.updated_at, which needs no
    # privilege of the invoking role.
    op.execute("REVOKE UPDATE ON pot_ownership_events FROM renly_app")
    op.execute("GRANT UPDATE (confirmed_at) ON pot_ownership_events TO renly_app")


# Puts the ledger back to one FOR ALL policy on write access and drops the column.
#
# Down-migrating discards every confirmation, which unlocks the entries that carried one; no figure
# anywhere is derived from the column, so every balance and percentage reads exactly as it did. The
# per-column grant is revoked before the table-level one is restored, so the role does not end up
# holding both.
def downgrade() -> None:
    op.execute("REVOKE UPDATE (confirmed_at) ON pot_ownership_events FROM renly_app")
    op.execute("GRANT UPDATE ON pot_ownership_events TO renly_app")
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_counterparty_delete ON pot_ownership_events")
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_confirm_update ON pot_ownership_events")
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_scope_delete ON pot_ownership_events")
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_scope_insert ON pot_ownership_events")
    op.execute(
        "CREATE POLICY pot_ownership_events_scope_write ON pot_ownership_events FOR ALL"
        " USING (app_can_write_pot(pot_id)) WITH CHECK (app_can_write_pot(pot_id))"
    )
    op.execute(
        """
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
    )
    op.drop_constraint("pot_ownership_events_confirmable", "pot_ownership_events", type_="check")
    op.drop_column("pot_ownership_events", "confirmed_at")
