# The overdue-valuation reminder (§9's third job for a pot's cadence), driven by the hourly scheduler.
#
# Cadence is an EXPECTATION, not a schedule — nothing here writes a snapshot. It says how often the
# people who co-own a pot agreed it would be re-valued, and this job tells them when the pot has fallen
# behind that.
#
# Five properties, each of which decides something about the shape below.
#
#   * IT FIRES AT EACH PERSON'S OWN LOCAL HOUR, exactly as the auto-expense job does. The scheduler
#     ticks hourly and this filters to the users whose local time is now the reminder hour, so nobody
#     is woken at 03:00 because the server keeps UTC. A pot's writers can be in different timezones, so
#     they are reached on different ticks — which is fine, because of the next property.
#
#   * IT IS IDEMPOTENT THROUGH THE DEDUPE KEY, not through state of its own. Every notification carries
#     `pot:<id>:<cadence period>`, and a partial unique index refuses the second one. So the job may run
#     any number of times, reach different people on different ticks, and still tell each person once
#     per period — with no "last reminded" column anywhere, which would have had to live on `pots` (a
#     per-pot answer to a per-user question) and would have needed its own reset rule when the period
#     rolled over.
#
#   * IT ASKS THE WRITERS, not every viewer. Only a member with write access can snapshot a shared
#     holding, so a nudge to re-value a pot goes to the people who can clear it. Every viewer already
#     sees the staleness on the pot page — that indicator is the passive half, and this is the active
#     one.
#
#   * IT NEVER COMPUTES A NAV. Freshness is a question about DATES, so `pot_service.get_freshness`
#     answers it in three cheap reads with no rate lookup at all — which also means the reminder cannot
#     be made wrong by whose currency preference it happened to run under. A NAV per pot per hour would
#     be ten queries times every pot in the database.
#
#   * IT PRUNES BEFORE IT MEASURES. The roster, the permissions and the timezones load once, in three
#     queries, and only pots with a writer at their local reminder hour are valued at all — which on any
#     given tick is a small fraction of them.

from collections import defaultdict
from datetime import UTC, datetime
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import cadence_period_key
from app.models.notification import NotificationEvent
from app.repositories import group_repository, pot_repository, user_settings_repository
from app.services import notification_service, pot_service
from app.utils.dates import local_hour_for_user, today_in_timezone

# Hour of day, in each user's own local timezone, at which an overdue pot is reported. Morning rather
# than the 01:00 the auto-expense job uses: that one is a silent background write nobody reads, whereas
# this is a message asking somebody to do something, and it should arrive when they are awake.
SNAPSHOT_REMINDER_HOUR_LOCAL = 9


# Tells the people who can re-value a pot that it has fallen behind its cadence.
#
# Runs on the PRIVILEGED session (the scheduler has no user context), and returns how many people were
# actually TOLD — not how many were offered a reminder, which for a pot that stays stale is the same
# people every day. The dedupe index decides the difference, so the scheduler's log stays honest.
# `now_utc` is injectable for tests, mirroring auto_expense_service.
async def send_due_reminders(session: AsyncSession, now_utc: datetime | None = None) -> int:
    now_utc = now_utc or datetime.now(UTC)
    pots = await pot_repository.list_all(session)
    if not pots:
        return 0

    group_ids = sorted({pot.group_id for pot in pots})
    timezones = await user_settings_repository.get_all_timezones(session)
    permissions_by_pot = await pot_repository.list_permissions_by_pots(session, [pot.id for pot in pots])
    members_by_group = await group_repository.list_members_by_groups(session, group_ids)
    # Batch-loaded with everything else rather than per pot: the copy names the group, and a lookup
    # inside the loop below is a query per pot however few of them have anybody to notify.
    group_names = {group.id: group.name for group in await group_repository.get_by_ids(session, group_ids)}

    dispatched = 0
    for pot in pots:
        writers = pot_service.writer_user_ids(pot, members_by_group.get(pot.group_id, []), permissions_by_pot.get(pot.id, []))
        # Grouped by each writer's own local DATE, because two people at their local reminder hour on
        # the same UTC tick can be on different calendar days — and the date is both what freshness is
        # measured against and what the dedupe key names. Normally one group.
        due_by_date: dict[date_type, list[int]] = defaultdict(list)
        for user_id in writers:
            timezone = timezones.get(user_id)
            if local_hour_for_user(now_utc, timezone) == SNAPSHOT_REMINDER_HOUR_LOCAL:
                due_by_date[today_in_timezone(now_utc, timezone)].append(user_id)
        if not due_by_date:
            continue

        for local_today, user_ids in due_by_date.items():
            valued_as_of, is_stale = await pot_service.get_freshness(session, pot, as_of_date=local_today)
            if not is_stale:
                continue
            # The count is what dispatch actually WROTE, not len(user_ids): a pot stays stale for the
            # rest of its period, so the offer is made every day and the dedupe index refuses all but
            # the first. Counting the offer would make the scheduler's log claim a daily reminder that
            # nobody received.
            dispatched += await notification_service.dispatch(
                NotificationEvent.snapshot_due,
                user_ids,
                {
                    "group_id": pot.group_id,
                    "group": group_names.get(pot.group_id),
                    "pot_id": pot.id,
                    "pot": pot.name,
                    # ISO, or null when the pot holds something nobody has ever valued — the two read as
                    # different sentences ("Last valued 12 Jul" against "It has never been valued").
                    "valued_as_of": valued_as_of.isoformat() if valued_as_of else None,
                },
                dedupe_key=f"pot:{pot.id}:{cadence_period_key(pot.snapshot_cadence, local_today)}",
            )
    return dispatched
