# The upcoming-bill reminder, driven by the hourly scheduler.
#
# A payment obligation is the one recurring thing in Renly that NOBODY charges automatically. A
# subscription and an instalment both produce an expense on their own (auto_expense_service writes it,
# after the fact, because Renly records those charges rather than making them); an obligation sits
# there until the person pays it in the real world and marks it paid. So it is the only one where a
# "this is coming up" message is both true and actionable — which is why this job exists and its
# subscription equivalent deliberately does not.
#
# Four properties, each of which decides something about the shape below.
#
#   * IT FIRES AT EACH PERSON'S OWN LOCAL HOUR, exactly as pot_reminder_service and the auto-expense
#     job do, at the same waking 09:00 the pot reminder uses: both are messages asking somebody to do
#     something, where the auto-expense job's 01:00 is a silent write nobody reads.
#
#   * IT IS IDEMPOTENT THROUGH THE DEDUPE KEY, not through state of its own. Every notification carries
#     `obligation:<id>:<due date>`, and the partial unique index refuses the second one — so the job may
#     run any number of times and each cycle is announced exactly once. Paying advances
#     `next_due_date`, which is what makes the NEXT cycle a different key rather than a repeat.
#
#   * IT LOOKS FORWARD AND NEVER BACK. The window is "due within the lead time", with no lower bound,
#     and that is deliberate rather than an omission: an overdue obligation's key is the key its cycle
#     already used, so the index refuses it and nobody is nagged about a bill they have already been
#     told about. A lower bound would only change which rows are scanned, never which are sent.
#
#   * IT PRUNES IN SQL FIRST. The date bound runs in the query, so a tick loads only obligations
#     plausibly due rather than every active one; the per-user local-date comparison below is the
#     correctness layer, the same division auto_expense_service draws.

import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from datetime import date as date_type

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import NotificationEvent
from app.models.payment_obligation import PaymentObligation
from app.repositories import payment_obligation_repository, user_settings_repository
from app.services import notification_service
from app.utils.dates import local_hour_for_user, today_in_timezone

logger = logging.getLogger(__name__)

# Hour of day, in each user's own local timezone, at which an upcoming bill is announced.
OBLIGATION_REMINDER_HOUR_LOCAL = 9

# How many days ahead of its due date a bill is announced. One message per cycle, not one per day: three
# days is enough to move money or pay it, and a second reminder for the same bill is the thing people
# turn notifications off over.
OBLIGATION_REMINDER_LEAD_DAYS = 3


# Inclusive SQL cutoff for the due-scan. A user's local "today" can lead the UTC date by up to 14 hours
# (UTC+14), so scanning one day past the lead covers every user's local window; the exact per-user
# comparison below still decides what is actually announced. Same bound, and the same reason, as
# auto_expense_service._scan_cutoff.
def _scan_cutoff(now_utc: datetime) -> date_type:
    return now_utc.date() + timedelta(days=OBLIGATION_REMINDER_LEAD_DAYS + 1)


# Tells each person about the bills coming due in the next few days.
#
# Runs on the PRIVILEGED session (the scheduler has no user context), and returns how many people were
# actually TOLD rather than how many were offered a reminder — a bill stays inside the window for the
# whole lead period, so the offer is made every day and the dedupe index refuses all but the first.
# Counting the offer would make the scheduler's log claim a daily reminder nobody received.
# `now_utc` is injectable for tests, mirroring auto_expense_service and pot_reminder_service.
async def send_due_reminders(session: AsyncSession, now_utc: datetime | None = None) -> int:
    now_utc = now_utc or datetime.now(UTC)
    obligations = await payment_obligation_repository.list_active_due(session, _scan_cutoff(now_utc))
    if not obligations:
        return 0

    timezones = await user_settings_repository.get_all_timezones(session)
    # Grouped by owner so the local-hour test is asked once per person rather than once per bill, which
    # for anybody with several bills is the same answer computed several times.
    by_user: dict[int, list[PaymentObligation]] = defaultdict(list)
    for obligation in obligations:
        by_user[obligation.user_id].append(obligation)

    dispatched = 0
    for user_id, owned in by_user.items():
        timezone = timezones.get(user_id)
        if local_hour_for_user(now_utc, timezone) != OBLIGATION_REMINDER_HOUR_LOCAL:
            continue
        # The user's own calendar day is what the window is measured against, for the same reason the
        # auto-expense job measures its cursor that way: a bill due on the 18th is "three days away" on
        # the reader's 15th, not on the server's.
        horizon = today_in_timezone(now_utc, timezone) + timedelta(days=OBLIGATION_REMINDER_LEAD_DAYS)
        for obligation in owned:
            if obligation.next_due_date > horizon:
                continue
            dispatched += await notification_service.dispatch(
                NotificationEvent.obligation_due,
                [user_id],
                {
                    "obligation_id": obligation.id,
                    "name": obligation.name,
                    "amount": str(obligation.amount),
                    "currency": obligation.currency,
                    # The key the copy reads its date from is literally `date` on both sides — the API
                    # spells it out in the email and the web formats it for the feed.
                    "date": obligation.next_due_date.isoformat(),
                },
                dedupe_key=f"obligation:{obligation.id}:{obligation.next_due_date.isoformat()}",
            )
    if dispatched:
        logger.info("Obligation reminders: told %d people about upcoming bills at %s UTC.", dispatched, now_utc.isoformat())
    return dispatched
