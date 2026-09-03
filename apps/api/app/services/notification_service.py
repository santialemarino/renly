# The notification layer: one dispatch function every producer calls, the feed reads behind it, and the
# per-user channel preferences.
#
# Five properties govern this file.
#
#   * DISPATCH IS ENTITY-AGNOSTIC. It takes user ids, an event and a payload, and knows nothing about
#     groups, pots or expenses. Who should hear about something is answered by whichever entity owns
#     the visibility rule (group_service and pot_service each expose one function for it), on the
#     request session that can already see those rows. That split is what lets a second module reuse
#     this layer unchanged.
#
#   * IT RUNS ON THE PRIVILEGED SESSION, and it has to. Fanning an event out writes a row per
#     RECIPIENT, and `notifications` deliberately has no INSERT policy — so no request path can write
#     into anybody's feed, including its own. Same posture as group creation and invite acceptance.
#
#   * IT NEVER RAISES, and it is always called AFTER the producer's commit. A notification is a
#     side-effect of something that already happened: a push service being down, or a stale email
#     credential, must not fail — or worse, roll back — the money write that produced it. Every failure
#     is logged and swallowed, exactly as the transactional email sends already are.
#
#   * A PREFERENCE IS AN OVERRIDE. Absence means the shipped default (app/domain/notification.py), so
#     nothing is ever seeded and a new event has an answer for every existing account the day it is
#     added.
#
#   * THE ROW IS THE RECORD OF DISPATCH, which is subtly more than "the feed entry". It is what makes a
#     repeating notification idempotent (the dedupe index), so a row is written whenever ANY channel is
#     on for the recipient and the "In app" switch hides it from the feed rather than preventing it.
#     Turning that switch back on reveals the history, and the alternative — not writing the row —
#     would leave the hourly reminder with nothing to deduplicate against and email somebody every hour.

import asyncio
import logging
from datetime import datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import AdminSessionLocal
from app.domain import NotFoundError, PushNotConfiguredError
from app.domain.notification import is_enabled_by_default
from app.models.notification import Notification, NotificationChannel, NotificationEvent
from app.models.push_subscription import PushSubscription
from app.models.user import User
from app.repositories import notification_repository, push_subscription_repository, user_repository
from app.schemas.notification import (
    NotificationFeedResponse,
    NotificationPreferenceResponse,
    NotificationPreferencesResponse,
    NotificationReadResponse,
    NotificationResponse,
)
from app.services import notification_templates, settings_service, web_push
from app.services.email_service import get_email_service

logger = logging.getLogger(__name__)

# Web paths the outgoing links point at. The API needs absolute URLs for email and push, so it owns a
# copy of these three — the same reason group_invite_service owns "/join" for the invite link. The
# in-app feed does NOT use them: the client builds each row's href from its own route constants, from
# the ids in the payload, so the app's routing stays in one place on the side that routes.
_GROUP_PATH = "/shared/{group_id}"
_POT_PATH = "/shared/pots/{pot_id}"
_SETTINGS_PATH = "/notifications"

# Events whose link is the POT rather than the group. Everything else is group activity, and an event
# of these three whose payload names no pot falls back to the group — which cannot currently happen,
# and is a fallback rather than a guard because a link is not worth a 500.
_POT_LINKED_EVENTS = frozenset({NotificationEvent.ownership_changed, NotificationEvent.pot_movement, NotificationEvent.snapshot_due})

# The most rows one feed request may return, whatever it asks for.
MAX_FEED_PAGE_SIZE = 50


# The absolute URL a notification points at, built from the ids its payload carries.
def _link(event: NotificationEvent, payload: dict) -> str:
    pot_id = payload.get("pot_id")
    if event in _POT_LINKED_EVENTS and pot_id is not None:
        return f"{settings.web_base_url}{_POT_PATH.format(pot_id=pot_id)}"
    return f"{settings.web_base_url}{_GROUP_PATH.format(group_id=payload.get('group_id'))}"


# Whether one channel is on for one user, given the overrides already loaded for them.
def _is_enabled(event: NotificationEvent, channel: NotificationChannel, overrides: dict[tuple, bool]) -> bool:
    explicit = overrides.get((event, channel))
    return is_enabled_by_default(event, channel) if explicit is None else explicit


# The events the caller has switched OFF for the feed, which every feed read excludes. Derived from the
# same override rows the preferences page reads, so the two can never describe different states.
def _hidden_events(overrides: dict[tuple, bool]) -> list[NotificationEvent]:
    return [event for event in NotificationEvent if not _is_enabled(event, NotificationChannel.in_app, overrides)]


# The caller's overrides as the flat {(event, channel): enabled} map the helpers above expect.
async def _overrides(session: AsyncSession, user_id: int) -> dict[tuple, bool]:
    rows = await notification_repository.list_preferences(session, user_id)
    return {(row.event, row.channel): row.enabled for row in rows}


# Sends one email, swallowing every failure: the notification is already in the recipient's feed, so a
# send outage must not surface anywhere. Mirrors group_invite_service._safe_send.
#
# The RENDER is inside the try as well as the send, and that is not belt-and-braces. A payload missing a
# field the copy interpolates raises a KeyError here, and these run inside an asyncio.gather whose
# failure would abandon the loop that deletes dead push subscriptions and stamps live ones. One bad
# payload must cost its own message and nothing else.
async def _send_email(user: User, event: NotificationEvent, payload: dict, locale: str, link: str) -> None:
    try:
        message = notification_templates.notification_email(
            user.email,
            event,
            payload,
            link=link,
            settings_link=f"{settings.web_base_url}{_SETTINGS_PATH}",
            locale=locale,
        )
        await get_email_service().send(message)
    except Exception:
        logger.warning("Failed to send a '%s' notification email.", event.value, exc_info=True)


# Sends one push to one browser and reports back whether that browser is gone.
#
# The push title is the group (or the pot, for a pot event with no group named) and the body carries no
# figures at all — a push renders on a lock screen where anyone holding the phone reads it, so the
# amount waits for the app. `url` is what the service worker opens on a click.
# It never raises, for the same reason _send_email does not: the caller loops over these results to
# delete dead subscriptions and stamp live ones, and one unrenderable payload must not cost that loop.
# A failure here reports "not sent, not gone", which leaves the subscription exactly as it was.
async def _send_push(
    client: httpx.AsyncClient, subscription: PushSubscription, event: NotificationEvent, payload: dict, locale: str, link: str
) -> tuple[PushSubscription, bool, bool]:
    try:
        body = notification_templates.push_body(event, payload, locale)
    except Exception:
        logger.warning("Failed to render a '%s' push notification.", event.value, exc_info=True)
        return (subscription, False, False)
    sent, gone = await web_push.send(
        client,
        web_push.PushTarget(endpoint=subscription.endpoint, p256dh=subscription.p256dh, auth=subscription.auth),
        {"title": payload.get("group") or payload.get("pot") or "Renly", "body": body, "url": link},
    )
    return (subscription, sent, gone)


# Tells a set of people that something happened.
#
# The ONE entry point every producer calls, after its own commit. `dedupe_key` makes the dispatch
# idempotent for a repeating notification: the same (user, event, key) is accepted once, so a job may
# attempt it on every tick and only the first attempt reaches anybody.
#
# The order is not arbitrary. Preferences are read first, so a recipient with every channel off costs
# nothing further; the rows go in next, and only the recipients who actually GAINED one are sent to —
# which is what stops a re-attempted reminder emailing somebody a second time.
#
# Returns how many people were actually TOLD, which is not how many were asked: a deduped repeat and a
# recipient with every channel off both return 0, and so does a failure. Every producer ignores it; the
# hourly reminder is what needs it, because a job that logs its recipient count would report the same
# figure every day of a period while the dedupe index quietly wrote nothing.
async def dispatch(
    event: NotificationEvent, user_ids: list[int], payload: dict, *, dedupe_key: str | None = None, now: datetime | None = None
) -> int:
    recipients = sorted(set(user_ids))
    if not recipients:
        return 0
    try:
        async with AdminSessionLocal() as admin_session:
            overrides = await notification_repository.preferences_by_user_ids(admin_session, recipients)
            wanted = [
                user_id for user_id in recipients if any(_is_enabled(event, channel, overrides.get(user_id, {})) for channel in NotificationChannel)
            ]
            if not wanted:
                return 0
            rows = [Notification(user_id=user_id, event=event, payload=payload, dedupe_key=dedupe_key) for user_id in wanted]
            if now is not None:
                for row in rows:
                    row.created_at = now
            written = await notification_repository.create_many(admin_session, rows)
            await admin_session.commit()
            if written:
                await _deliver(admin_session, event, payload, written, overrides)
            return len(written)
    except Exception:
        logger.exception("Notification dispatch failed for event '%s'.", event.value)
        return 0


# Sends the out-of-app channels to the recipients who gained a row. Split from dispatch because the
# in-app half is a transaction and this half is a fan of network calls, and only the first must be
# atomic.
#
# Email and push go out in PARALLEL (independent external calls, per the performance rules) — a group
# of six with email on would otherwise be six sequential provider round trips inside the request that
# produced the event.
async def _deliver(
    admin_session: AsyncSession, event: NotificationEvent, payload: dict, written: list[int], overrides: dict[int, dict[tuple, bool]]
) -> None:
    email_ids = [user_id for user_id in written if _is_enabled(event, NotificationChannel.email, overrides.get(user_id, {}))]
    push_ids = (
        [user_id for user_id in written if _is_enabled(event, NotificationChannel.push, overrides.get(user_id, {}))]
        if web_push.is_configured()
        else []
    )
    if not email_ids and not push_ids:
        return

    # Every read the sends need, batch-loaded before any of them: the addresses, the languages, and the
    # subscribed browsers. One query each, whatever the size of the group.
    link = _link(event, payload)
    needed = sorted(set(email_ids) | set(push_ids))
    users = await user_repository.get_by_ids(admin_session, needed)
    languages = await settings_service.get_languages_by_user_ids(admin_session, needed)
    subscriptions = await push_subscription_repository.list_by_user_ids(admin_session, push_ids) if push_ids else {}
    push_targets = [(user_id, sub) for user_id in push_ids if user_id in users for sub in subscriptions.get(user_id, [])]

    async with httpx.AsyncClient() as client:
        _, push_results = await asyncio.gather(
            asyncio.gather(*(_send_email(users[user_id], event, payload, languages[user_id], link) for user_id in email_ids if user_id in users)),
            asyncio.gather(*(_send_push(client, sub, event, payload, languages[user_id], link) for user_id, sub in push_targets)),
        )

    # A subscription the push service reported gone is dead: the browser revoked it or was reinstalled.
    # Deleted here rather than left to fail forever, and touched on success so a person can tell which
    # of their devices is still live.
    for subscription, sent, gone in push_results:
        if gone:
            await push_subscription_repository.delete_by_endpoint(admin_session, subscription.endpoint)
        elif sent:
            await push_subscription_repository.touch(admin_session, subscription.id)
    await admin_session.commit()


# One page of the caller's feed, plus the totals the badge and the paging need — all three describing
# the same set of rows, because they share one filter.
async def get_feed(session: AsyncSession, user: User, *, limit: int, offset: int = 0) -> NotificationFeedResponse:
    hidden = _hidden_events(await _overrides(session, user.id))
    page = min(limit, MAX_FEED_PAGE_SIZE)
    items = await notification_repository.list_by_user(session, user.id, limit=page, offset=offset, exclude_events=hidden)
    total = await notification_repository.count_by_user(session, user.id, exclude_events=hidden)
    unread = await notification_repository.count_unread(session, user.id, exclude_events=hidden)
    return NotificationFeedResponse(
        items=[NotificationResponse.model_validate(item) for item in items],
        total=total,
        unread=unread,
    )


# Marks one notification read. Raises NotFoundError for a row that is not the caller's, so an id from
# somebody else's feed is indistinguishable from one that does not exist.
async def mark_read(session: AsyncSession, notification_id: int, user: User) -> NotificationReadResponse:
    hidden = _hidden_events(await _overrides(session, user.id))
    notification = await notification_repository.get_by_id(session, user.id, notification_id)
    if notification is None:
        raise NotFoundError("Notification not found")
    updated = 0 if notification.read_at is not None else 1
    await notification_repository.mark_read(session, notification)
    await session.commit()
    unread = await notification_repository.count_unread(session, user.id, exclude_events=hidden)
    return NotificationReadResponse(updated=updated, unread=unread)


# Marks every notification the caller can see read. Deliberately scoped by the same exclusion the reads
# use: the button clears exactly what the list was showing.
async def mark_all_read(session: AsyncSession, user: User) -> NotificationReadResponse:
    hidden = _hidden_events(await _overrides(session, user.id))
    updated = await notification_repository.mark_all_read(session, user.id, exclude_events=hidden)
    await session.commit()
    unread = await notification_repository.count_unread(session, user.id, exclude_events=hidden)
    return NotificationReadResponse(updated=updated, unread=unread)


# The full preferences grid — every event on every channel — plus what this deployment can do.
#
# The grid is BUILT rather than read: the table holds only overrides, so the response walks both enums
# and reports the default wherever there is no row. `is_default` says which is which, so the surface can
# show a switch nobody has touched without pretending somebody chose it.
async def get_preferences(session: AsyncSession, user: User) -> NotificationPreferencesResponse:
    overrides = await _overrides(session, user.id)
    subscriptions = await push_subscription_repository.list_by_user(session, user.id)
    return NotificationPreferencesResponse(
        preferences=[
            NotificationPreferenceResponse(
                event=event,
                channel=channel,
                enabled=_is_enabled(event, channel, overrides),
                is_default=(event, channel) not in overrides,
            )
            for event in NotificationEvent
            for channel in NotificationChannel
        ],
        push_available=web_push.is_configured(),
        push_public_key=web_push.public_key(),
        push_subscriptions=len(subscriptions),
    )


# Records the caller's answer for one switch and returns the whole grid, so the client re-renders from
# one source rather than patching its own copy.
async def set_preference(
    session: AsyncSession, user: User, *, event: NotificationEvent, channel: NotificationChannel, enabled: bool
) -> NotificationPreferencesResponse:
    await notification_repository.save_preference(session, user.id, event, channel, enabled=enabled)
    await session.commit()
    return await get_preferences(session, user)


# Registers the calling browser for web push, or refreshes the keys of one already registered.
#
# Idempotent by construction: the endpoint identifies the browser, so re-subscribing after a page
# reload replaces the row rather than adding one. A deployment with no VAPID key refuses instead of
# storing a subscription nothing will ever send to — a switch that reads as on and delivers nothing is
# worse than one that is honestly unavailable.
#
# The release step first, on the privileged session, is what makes a SHARED BROWSER correct — and a
# shared-money app is exactly where two accounts sign in on one computer. A browser holds one push
# subscription, so the endpoint the second account presents is the one the first is registered under.
# Without this the caller's own connection cannot take it over (the owner-match policy refuses an
# update it cannot see, so subscribing would 500) and, worse, the first account's row would survive and
# keep pushing their group activity onto a browser somebody else is now signed in on.
async def subscribe_push(
    session: AsyncSession, user: User, *, endpoint: str, p256dh: str, auth: str, user_agent: str | None = None
) -> NotificationPreferencesResponse:
    if not web_push.is_configured():
        raise PushNotConfiguredError()
    async with AdminSessionLocal() as admin_session:
        await push_subscription_repository.release_endpoint(admin_session, endpoint, keep_user_id=user.id)
        await admin_session.commit()
    await push_subscription_repository.upsert(
        session,
        PushSubscription(user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth, user_agent=user_agent),
    )
    await session.commit()
    return await get_preferences(session, user)


# Stops sending push to one browser. Idempotent: unsubscribing something already gone is not an error,
# since the caller's intent ("this browser must not be pushed to") is satisfied either way — the same
# reasoning as revoking a group invite.
async def unsubscribe_push(session: AsyncSession, user: User, *, endpoint: str) -> NotificationPreferencesResponse:
    await push_subscription_repository.delete_by_endpoint(session, endpoint)
    await session.commit()
    return await get_preferences(session, user)
