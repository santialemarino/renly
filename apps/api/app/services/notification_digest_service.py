# The daily email digest, driven by the hourly scheduler.
#
# A digest changes WHEN an email leaves and nothing else. Every notification row is still written at
# dispatch, the feed and the unread badge behave exactly as they always have, and push is untouched —
# somebody who asked for fewer emails did not ask for delayed alerts. It is the third answer between
# "off" and "one email per event", and it is what makes the noisy events safe to turn on at all.
#
# Five properties, each of which decides something about the shape below.
#
#   * IT NEEDS NO PER-EVENT COPY. Each line of the email is that event's own email SUBJECT, which is
#     already the one-sentence form of it. So an event added later is digestible the day it exists, and
#     the list of enumerated lists a new event has to be added to does not grow by one more.
#
#   * THE QUEUE IS A PER-ROW FLAG, not a per-user cursor. `notifications.digest_pending` is written at
#     dispatch, by the one predicate that also decides the email is not sent immediately, so the two can
#     never disagree. A cursor would have to be initialised the moment somebody switched cadence, and
#     getting that wrong emails them a summary of their entire history.
#
#   * IT PRUNES BEFORE IT MEASURES, like the overdue-valuation reminder. The first read is "who is owed
#     a summary", which a partial index answers in one probe — so an hour with an empty queue loads no
#     timezone, no user and no notification. Everything else is batched over the people that read
#     returns.
#
#   * IT FIRES AT EACH PERSON'S OWN LOCAL HOUR, in the EVENING. Deliberately later in the day than the
#     two reminder jobs, which run at local 09:00: both jobs and this one filter on the SAME person's
#     local clock, so a reminder raised this morning is always already queued when this evening's digest
#     is built. That relationship holds in every timezone and depends on no job ordering.
#
#   * IT CLEARS THE QUEUE WHETHER OR NOT THE SEND SUCCEEDS. The notifications are already in the
#     recipient's feed, so a provider outage must not leave a queue that re-sends the same summary every
#     day until it recovers — the same posture every other send in this layer takes.

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.notification import Notification
from app.repositories import notification_repository, user_repository, user_settings_repository
from app.services import notification_templates, settings_service
from app.services.email_service import EmailMessage, get_email_service
from app.utils.dates import local_hour_for_user

logger = logging.getLogger(__name__)

# Hour of day, in each user's own local timezone, at which the daily summary is sent. Evening rather
# than the 09:00 the two reminder jobs use, so a reminder raised this morning reaches TODAY's summary
# rather than tomorrow's — see the fourth property above.
DIGEST_HOUR_LOCAL = 20

# The most rows one digest email spells out. A heavy day must produce a readable message rather than a
# five-hundred-line one; the count of what was left out is stated in the email, and every row is in the
# feed the email links to, so nothing is lost by capping.
DIGEST_MAX_ITEMS = 40

# The notifications page: both where the whole history lives and where the cadence is changed, so the
# digest's own "see them all" link and the standard footer point at the same place.
_NOTIFICATIONS_PATH = "/notifications"


# Sends each person who asked for a daily summary the one email they are owed.
#
# Runs on the PRIVILEGED session (the scheduler has no user context, and the queue spans every user).
# Returns how many digest emails were composed and handed to the sender — not how many people are on
# the daily cadence, which for anybody with a quiet day is a larger number and a false one.
# `now_utc` is injectable for tests, mirroring pot_reminder_service.
async def send_due_digests(session: AsyncSession, now_utc: datetime | None = None) -> int:
    now_utc = now_utc or datetime.now(UTC)
    pending_user_ids = await notification_repository.list_digest_pending_user_ids(session)
    if not pending_user_ids:
        return 0

    timezones = await user_settings_repository.get_all_timezones(session)
    due_user_ids = [user_id for user_id in pending_user_ids if local_hour_for_user(now_utc, timezones.get(user_id)) == DIGEST_HOUR_LOCAL]
    if not due_user_ids:
        return 0

    pending = await notification_repository.list_digest_pending(session, due_user_ids)
    users = await user_repository.get_by_ids(session, due_user_ids)
    languages = await settings_service.get_languages_by_user_ids(session, due_user_ids)

    link = f"{settings.web_base_url}{_NOTIFICATIONS_PATH}"
    sent = 0
    cleared: list[int] = []
    messages: list[EmailMessage] = []
    for user_id in due_user_ids:
        rows = pending.get(user_id, [])
        # Every row this tick read is cleared, including a deleted user's: leaving it pending would keep
        # the queue — and so this job's first read — describing somebody who can never be emailed.
        cleared.extend(row.id for row in rows)
        user = users.get(user_id)
        if user is None or not rows:
            continue
        messages.append(_digest_for(user.email, rows, languages[user_id], link))
        sent += 1

    # The sends go out in PARALLEL (independent external calls, per the performance rules) and the
    # queue is cleared in the SAME transaction the tick commits, so a crash between the two cannot lose
    # a summary silently: the rows stay pending and the next tick rebuilds them.
    await asyncio.gather(*(_send(message) for message in messages))
    await notification_repository.clear_digest_pending(session, cleared)
    await session.commit()
    if sent:
        logger.info("Notification digests: sent %d summaries at %s UTC.", sent, now_utc.isoformat())
    return sent


# Builds one person's digest from their pending rows, capping what it spells out and naming the rest.
def _digest_for(email: str, rows: list[Notification], locale: str, link: str) -> EmailMessage:
    shown = rows[:DIGEST_MAX_ITEMS]
    return notification_templates.digest_email(
        email,
        [(row.event, row.payload) for row in shown],
        link=link,
        settings_link=link,
        overflow=len(rows) - len(shown),
        locale=locale,
    )


# Sends one digest, swallowing every failure — the notifications are already in the recipient's feed,
# so a send outage must not surface anywhere. Mirrors notification_service._send_email, and matters
# more here: these run inside an asyncio.gather whose failure would abandon the rest of the batch.
async def _send(message: EmailMessage) -> None:
    try:
        await get_email_service().send(message)
    except Exception:
        logger.warning("Failed to send a notification digest.", exc_info=True)
