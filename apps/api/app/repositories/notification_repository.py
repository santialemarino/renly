# Data access for the notification feed and the per-user channel preferences.
#
# Two sessions reach this file and the difference is load-bearing. The READS and the mark-read/delete
# writes run on the request session, where the owner-match policies scope them. `create_many` runs on
# the PRIVILEGED session and can only run there: fanning one event out writes a row per recipient, and
# `notifications` has no INSERT policy at all, precisely so no request path can write into anybody's
# feed. See the migration for why that is the design rather than an omission.

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.notification import Notification, NotificationChannel, NotificationEvent, NotificationPreference
from app.models.utils import utcnow


# The three feed reads share one WHERE, which is the point: the list, the total and the unread badge
# have to describe the same set of rows, and three separately-written predicates are three things that
# can disagree — the badge saying 2 above a list showing none.
#
# `exclude_events` is how the "In app" switch is honoured. A row is written whenever ANY channel is on
# for the recipient, because the row is also what stops a repeating notification repeating (see the
# dedupe index); turning the feed off for an event therefore hides it here rather than preventing it,
# and turning it back on reveals the history. Passing the same list to all three is what keeps them
# agreeing.
def _feed_filter(user_id: int, exclude_events: list[NotificationEvent] | None):
    clauses = [Notification.user_id == user_id]
    if exclude_events:
        clauses.append(Notification.event.notin_(exclude_events))
    return clauses


# Lists the caller's notifications, newest first, one page at a time.
async def list_by_user(
    session: AsyncSession, user_id: int, *, limit: int, offset: int = 0, exclude_events: list[NotificationEvent] | None = None
) -> list[Notification]:
    result = await session.execute(
        select(Notification)
        .where(*_feed_filter(user_id, exclude_events))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


# How many notifications the caller can see in total, for the feed's paging.
async def count_by_user(session: AsyncSession, user_id: int, *, exclude_events: list[NotificationEvent] | None = None) -> int:
    result = await session.execute(select(func.count()).select_from(Notification).where(*_feed_filter(user_id, exclude_events)))
    return int(result.scalar_one())


# How many of the caller's visible notifications are unread — the badge's figure.
async def count_unread(session: AsyncSession, user_id: int, *, exclude_events: list[NotificationEvent] | None = None) -> int:
    result = await session.execute(
        select(func.count()).select_from(Notification).where(*_feed_filter(user_id, exclude_events), Notification.read_at.is_(None))
    )
    return int(result.scalar_one())


# Fetches one of the caller's notifications, or None. The owner filter is stated as well as enforced by
# RLS, so the function is correct on the privileged session too.
async def get_by_id(session: AsyncSession, user_id: int, notification_id: int) -> Notification | None:
    result = await session.execute(select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id))
    return result.scalar_one_or_none()


# Writes a batch of notifications, skipping any the dedupe index already holds.
#
# ON CONFLICT DO NOTHING is what makes a repeating notification safe to attempt on every tick: the
# hourly overdue reminder re-offers the same (user, event, dedupe_key) all period and the index refuses
# all but the first, so the job needs no state of its own. It targets the partial index by repeating its
# predicate — Postgres matches a partial index only when the statement names the same WHERE — so rows
# with a NULL key are simply inserted and never deduplicated.
#
# The arbiter names its columns rather than being a bare DO NOTHING, which would behave identically
# here and be strictly worse: a bare one swallows a conflict on ANY constraint, so a genuine bug on some
# other index would become a row that silently failed to insert. Naming the arbiter means only the
# dedupe collision is tolerated and anything else still raises.
#
# Returns the user ids that actually GAINED a row, which is what the caller needs and all of it: email
# and push must go to exactly those recipients, never to the ones a previous tick already told. Columns
# are listed explicitly rather than dumped from the models so every row of the batch carries the same
# keys — a multi-row VALUES with differing keys is not the same statement.
async def create_many(admin_session: AsyncSession, notifications: list[Notification]) -> list[int]:
    if not notifications:
        return []
    stmt = (
        insert(Notification)
        .values(
            [
                {
                    "user_id": n.user_id,
                    "event": n.event,
                    "payload": n.payload,
                    "dedupe_key": n.dedupe_key,
                    "created_at": n.created_at,
                }
                for n in notifications
            ]
        )
        .on_conflict_do_nothing(
            index_elements=["user_id", "event", "dedupe_key"],
            index_where=Notification.dedupe_key.is_not(None),
        )
        .returning(Notification.user_id)
    )
    result = await admin_session.execute(stmt)
    return list(result.scalars().all())


# Marks one notification read, if it is not already. Returns the row so the caller can respond with it.
async def mark_read(session: AsyncSession, notification: Notification, *, now: datetime | None = None) -> Notification:
    if notification.read_at is None:
        notification.read_at = now or utcnow()
        session.add(notification)
        await session.flush()
    return notification


# Marks every unread notification the caller can SEE as read, in one statement. It takes the same
# exclusion the reads take, so "mark all read" clears exactly the rows the list was showing — without
# it the button would silently touch rows the user has hidden and the badge would still be right.
# Returns how many changed, so the response can say nothing happened rather than claiming it did.
async def mark_all_read(
    session: AsyncSession, user_id: int, *, exclude_events: list[NotificationEvent] | None = None, now: datetime | None = None
) -> int:
    result = await session.execute(
        update(Notification)
        .where(*_feed_filter(user_id, exclude_events), Notification.read_at.is_(None))
        .values(read_at=now or utcnow())
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


# Lists every preference OVERRIDE the user holds. Absence of a row means the shipped default, so the
# caller merges this over the defaults rather than expecting a full grid.
async def list_preferences(session: AsyncSession, user_id: int) -> list[NotificationPreference]:
    result = await session.execute(select(NotificationPreference).where(NotificationPreference.user_id == user_id))
    return list(result.scalars().all())


# Batch variant of list_preferences: {user_id: {(event, channel): enabled}} for every requested id, in
# one query. The fan-out asks about every recipient of an event at once, so the single-user version
# inside that loop would be an N+1 that grows with the group.
async def preferences_by_user_ids(session: AsyncSession, user_ids: list[int]) -> dict[int, dict[tuple[NotificationEvent, NotificationChannel], bool]]:
    if not user_ids:
        return {}
    result = await session.execute(select(NotificationPreference).where(NotificationPreference.user_id.in_(user_ids)))
    by_user: dict[int, dict[tuple[NotificationEvent, NotificationChannel], bool]] = defaultdict(dict)
    for row in result.scalars().all():
        by_user[row.user_id][(row.event, row.channel)] = row.enabled
    return dict(by_user)


# Records the user's explicit answer for one event on one channel, replacing any previous one.
#
# An upsert rather than a read-then-write: the unique constraint is the arbiter, so two tabs saving the
# same switch cannot leave two rows or raise. updated_at is set explicitly because ON CONFLICT DO UPDATE
# is a write the BEFORE UPDATE trigger does fire for, but naming it keeps the value the same whichever
# branch ran.
async def save_preference(session: AsyncSession, user_id: int, event: NotificationEvent, channel: NotificationChannel, *, enabled: bool) -> None:
    now = utcnow()
    stmt = (
        insert(NotificationPreference)
        .values(user_id=user_id, event=event, channel=channel, enabled=enabled, created_at=now, updated_at=now)
        .on_conflict_do_update(constraint="notification_preferences_once", set_={"enabled": enabled, "updated_at": now})
    )
    await session.execute(stmt)


# Namespace to call repository functions (e.g. notification_repository.list_by_user).
class NotificationRepository:
    list_by_user = staticmethod(list_by_user)
    count_by_user = staticmethod(count_by_user)
    count_unread = staticmethod(count_unread)
    get_by_id = staticmethod(get_by_id)
    create_many = staticmethod(create_many)
    mark_read = staticmethod(mark_read)
    mark_all_read = staticmethod(mark_all_read)
    list_preferences = staticmethod(list_preferences)
    preferences_by_user_ids = staticmethod(preferences_by_user_ids)
    save_preference = staticmethod(save_preference)


# Singleton used by services to access notification persistence.
notification_repository = NotificationRepository()
