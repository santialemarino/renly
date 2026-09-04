from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, String, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow

# Both string columns are capped here rather than at the request boundary, because nothing outside this
# API ever supplies either value — every write names a member of the two enums below.
ENTITY_TYPE_LENGTH = 50
ACTION_LENGTH = 50


# What kind of shared thing an entry is about.
#
# Stored as a plain VARCHAR rather than a Postgres enum, unlike every other enum in this schema, and
# that is the point: the audit log is the last piece of the membership kernel that had to stay
# entity-agnostic, so a second module adds an entity type by adding a member here and needs no
# migration at all. The values name no money concept in the TABLE — `shared_expense` and `settlement`
# are entities the money module happens to own, exactly as `notification_event`'s labels are.
class AuditEntityType(StrEnum):
    group = "group"
    group_invite = "group_invite"
    group_member = "group_member"
    group_money_settings = "group_money_settings"
    ownership_event = "ownership_event"
    pot = "pot"
    settlement = "settlement"
    shared_expense = "shared_expense"
    shared_income = "shared_income"


# What was done to it. Verbs only, and a small set deliberately reused across entity types: what
# distinguishes "a contribution was recorded" from "a withdrawal was recorded" is the payload's
# `variant`, not a third action — the same split PR 7 made between an event and its variant, and for
# the same reason. A new action is a new sentence to translate; a new variant is a new line under one.
class AuditAction(StrEnum):
    added = "added"
    confirmed = "confirmed"
    created = "created"
    deleted = "deleted"
    holdings_added = "holdings_added"
    holdings_removed = "holdings_removed"
    joined = "joined"
    leg_set = "leg_set"
    permission_cleared = "permission_cleared"
    permission_set = "permission_set"
    removed = "removed"
    revoked = "revoked"
    unconfirmed = "unconfirmed"
    updated = "updated"


# One entry in a group's audit trail: who did what to which shared entity, and when.
#
# The row stores an entity, an action and a PAYLOAD — never a rendered sentence — for the reason the
# notification layer stores the same shape: the prose is assembled in the reader's own language at
# render time, so the feed reads correctly for every member whatever locale each of them uses, and a
# copy fix reaches rows written months ago.
#
# `pot_id` is what keeps the log from disclosing what a policy hides. A pot may be invisible to a
# member ('owners' visibility, or an explicit can_view false), so an entry about one carries its id and
# the RLS policy adds `pot_id IS NULL OR app_can_view_pot(pot_id)` on top of group membership —
# reusing the SAME helper the pot tables use rather than adding a third copy of that rule.
#
# It carries NO foreign key, and that is deliberate: an audit entry has to outlive the thing it
# describes, and a CASCADE would delete a pot's whole history at the moment somebody deleted the pot —
# the one act most worth having a record of. app_can_view_pot answers false for a pot that no longer
# exists, so a deleted pot's earlier entries go dark rather than becoming group-visible. The
# `pot.deleted` entry itself is written with pot_id NULL, because what it discloses is a pot's name and
# who removed it — group administration, and by then the pot provably held nothing.
#
# `entity_id` is a plain BIGINT for the same reason and one more: the entity it names lives in one of
# nine tables, so no single foreign key could express it.
class SharedAuditEntry(SQLModel, table=True):
    __tablename__ = "shared_audit_log"

    id: int | None = Field(default=None, primary_key=True)
    group_id: int = Field(foreign_key="groups.id", description="Group whose trail this belongs to.")
    actor_user_id: int | None = Field(default=None, foreign_key="users.id", description="Who did it; NULL once that account is deleted.")
    entity_type: AuditEntityType = Field(sa_column=Column(String(ENTITY_TYPE_LENGTH), nullable=False))
    entity_id: int | None = Field(default=None, description="Its id, or NULL for an entity keyed by the group itself.")
    action: AuditAction = Field(sa_column=Column(String(ACTION_LENGTH), nullable=False))
    pot_id: int | None = Field(default=None, description="Pot this concerns, so the entry is hidden wherever the pot is. No FK, by design.")
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="Values the copy interpolates, plus the ids a deep link is built from.",
    )
    created_at: datetime = Field(default_factory=utcnow)
