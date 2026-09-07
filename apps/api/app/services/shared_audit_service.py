# The audit trail for shared entities: one record function every producer calls, and the group's
# activity read behind it.
#
# Four properties govern this file, and each is the mirror of one the notification layer already has.
#
#   * IT IS ENTITY-AGNOSTIC. `record` takes a group, an actor, an entity type, an id and a payload, and
#     knows nothing about pots, expenses or settlements. Nothing here imports a money model. That is
#     what lets a second module over the same membership kernel reuse the table, the policy and this
#     function unchanged — the last piece that had to stay reusable (`house-app-brief.md` §2).
#
#   * IT RUNS ON THE PRODUCER'S OWN SESSION AND DOES NOT COMMIT, which is the opposite of dispatch()
#     and deliberately so. A notification is a side-effect of something that already happened, so it
#     must never fail the write; an audit entry is part of the same fact, so it must never survive a
#     write that rolled back — nor go missing from one that did not. It is written BEFORE the
#     producer's commit and rides it.
#
#     One ordering rule falls out of that, and it is the only thing a producer has to remember: AN ACT
#     THAT REVOKES THE ACTOR'S OWN ACCESS RECORDS ITSELF FIRST. The policy's WITH CHECK asks whether
#     the writer is a member of the group and may see the pot, so leaving a group, or clearing your own
#     view of a pot, would refuse the very entry that says you did it. `record` therefore FLUSHES, so
#     calling it before the revocation is enough — there are three such call sites and each is tested.
#
#   * THE ROW STORES STRUCTURE, NEVER PROSE. `entity_type.action` is a translation key and `payload`
#     holds what that key interpolates, so the activity feed reads in whatever language its reader is
#     using now and a copy fix reaches entries written months ago. Same reason `notifications` stores a
#     payload rather than a sentence.
#
#   * WHAT THE FEED DISCLOSES IS THE DATABASE'S ANSWER, not this file's. An entry naming a pot carries
#     `pot_id`, and the RLS policy hides it from anyone the pot itself is hidden from. There is no
#     Python filter here to keep in step with the policy, because a second copy of a visibility rule is
#     the thing that eventually disagrees with the first.

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.shared_audit import AuditAction, AuditEntityType, SharedAuditEntry
from app.models.user import User
from app.repositories import group_repository, shared_audit_repository
from app.schemas.shared_audit import SharedAuditEntryResponse

# The most entries one activity read may return, whatever it asks for. Mirrors the notification feed's
# own cap, and for the same reason: this table only grows.
MAX_ACTIVITY_PAGE_SIZE = 50

# What the group hub asks for when it asks for nothing in particular.
DEFAULT_ACTIVITY_PAGE_SIZE = 20


# Records one act against a shared entity, on the caller's own session and without committing.
#
# `actor_user_id` rather than an actor's NAME. The name is resolved at READ time from the group's
# roster, so it follows a rename and a placeholder-to-account upgrade, where a name copied in here
# would be a second answer that goes stale silently — and the feed reads the roster anyway.
#
# `pot_id` is passed by every producer whose act concerns a pot — including the ones whose entity is
# not the pot itself (an ownership event, a holdings move) — because it is what the policy reads to
# decide who may see the entry, and an entry that omits it is visible to the whole group.
async def record(
    session: AsyncSession,
    *,
    group_id: int,
    actor: User | None,
    entity_type: AuditEntityType,
    action: AuditAction,
    entity_id: int | None = None,
    pot_id: int | None = None,
    payload: dict | None = None,
) -> SharedAuditEntry:
    entry = shared_audit_repository.create(
        session,
        SharedAuditEntry(
            group_id=group_id,
            actor_user_id=actor.id if actor is not None else None,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            pot_id=pot_id,
            payload=payload or {},
        ),
    )
    # Flushed here rather than left to the commit, so the INSERT is evaluated against the world as it
    # stands NOW. See the ordering rule in the module comment: without this, an entry recorded before a
    # self-revocation would still be sent to the database after it, and refused by its own policy.
    await session.flush()
    return entry


# A group's recent activity, newest first, and only what the caller may see.
#
# Two visibility rules apply and they are enforced in different places on purpose: membership and the
# pot branch come from the table's RLS policy (so a non-member's read is empty rather than refused),
# while `group_service.require_member` above turns "not a member" into the same 404 every other group
# read gives — without it a stranger would get an empty list, which says a group with that id exists.
async def list_activity(session: AsyncSession, group_id: int, user: User, *, limit: int) -> list[SharedAuditEntryResponse]:
    from app.services import group_service

    await group_service.require_member(session, group_id, user)
    entries = await shared_audit_repository.list_by_group(session, group_id, limit=min(limit, MAX_ACTIVITY_PAGE_SIZE))

    # Actor names come from the group's ROSTER, not from `users`, and that is not a preference: the
    # `users` policy is an owner match, so a request session can read exactly one row — its own — and
    # every other actor would come back nameless. The roster is the right source anyway. It is what
    # every other group surface names people by, it keeps the seat of a REMOVED member (deactivated,
    # never deleted), and a placeholder seat carries the name the group actually knows that person by.
    # One query for the page, since the roster is already bounded by the group's size.
    names = {member.user_id: member.display_name for member in await group_repository.list_members(session, group_id) if member.user_id is not None}
    return [
        SharedAuditEntryResponse(
            id=entry.id,
            entity_type=entry.entity_type,
            entity_id=entry.entity_id,
            action=entry.action,
            pot_id=entry.pot_id,
            # None rather than "" for a deleted account, so the renderer can say "somebody" in the
            # reader's own language instead of printing an empty name into the middle of a sentence.
            actor_name=names.get(entry.actor_user_id) if entry.actor_user_id is not None else None,
            payload=entry.payload,
            created_at=entry.created_at,
        )
        for entry in entries
    ]
