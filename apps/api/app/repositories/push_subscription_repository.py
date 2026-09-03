# Data access for web-push subscriptions.
#
# The rows hold the encryption secrets a push is sealed with, so nothing here ever logs a row and no
# read is offered that spans users — `list_by_user_ids` is the fan-out's batch read and runs on the
# privileged session, exactly as the notification insert does.

from collections import defaultdict
from datetime import datetime

from sqlalchemy import delete as sa_delete
from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.push_subscription import PushSubscription
from app.models.utils import utcnow


# Lists the browsers one account has subscribed, oldest first.
async def list_by_user(session: AsyncSession, user_id: int) -> list[PushSubscription]:
    result = await session.execute(select(PushSubscription).where(PushSubscription.user_id == user_id).order_by(PushSubscription.id))
    return list(result.scalars().all())


# Batch variant of list_by_user: {user_id: [subscription, ...]} for every requested id, in one query.
# The fan-out sends to every recipient of an event at once, so the single-user version inside that loop
# would be a query per recipient.
async def list_by_user_ids(session: AsyncSession, user_ids: list[int]) -> dict[int, list[PushSubscription]]:
    if not user_ids:
        return {}
    result = await session.execute(select(PushSubscription).where(PushSubscription.user_id.in_(user_ids)))
    by_user: dict[int, list[PushSubscription]] = defaultdict(list)
    for row in result.scalars().all():
        by_user[row.user_id].append(row)
    return dict(by_user)


# Registers a browser, or refreshes the keys of one already registered.
#
# An upsert on `endpoint` and not on (user_id, endpoint), because the endpoint identifies the BROWSER
# globally: one browser has one push subscription, so two accounts cannot each hold a live one. The
# keys are re-read on every subscribe because a browser may rotate them without changing the endpoint.
#
# On a REQUEST session this can only ever insert a new row or refresh the caller's own — the conflict
# target is checked against the owner-match policy, so a row belonging to somebody else raises rather
# than moving. Handing the browser to its new owner is `release_endpoint`, which the service runs first
# on the privileged session.
async def upsert(session: AsyncSession, subscription: PushSubscription) -> None:
    stmt = (
        insert(PushSubscription)
        .values(
            user_id=subscription.user_id,
            endpoint=subscription.endpoint,
            p256dh=subscription.p256dh,
            auth=subscription.auth,
            user_agent=subscription.user_agent,
            created_at=subscription.created_at,
        )
        .on_conflict_do_update(
            constraint="push_subscriptions_endpoint_once",
            set_={
                "user_id": subscription.user_id,
                "p256dh": subscription.p256dh,
                "auth": subscription.auth,
                "user_agent": subscription.user_agent,
            },
        )
    )
    await session.execute(stmt)


# Records that a send to this browser succeeded. Runs on the privileged session with the sender.
async def touch(session: AsyncSession, subscription_id: int, *, now: datetime | None = None) -> None:
    await session.execute(update(PushSubscription).where(PushSubscription.id == subscription_id).values(last_used_at=now or utcnow()))


# Removes one browser's subscription by its endpoint.
#
# Two callers, and the second is why this takes no user_id: the user unsubscribing their own browser
# (RLS scopes it to them), and the SENDER discarding a subscription the push service reported gone —
# which runs on the privileged session for a row that is not the sender's to begin with.
async def delete_by_endpoint(session: AsyncSession, endpoint: str) -> None:
    await session.execute(sa_delete(PushSubscription).where(PushSubscription.endpoint == endpoint))


# Detaches a browser from every account except the one about to claim it. Privileged session only.
#
# What it exists for: one browser holds ONE push subscription, so when a second account signs in on it
# and enables push, the endpoint the browser reports is the endpoint the first account is registered
# under. Leaving that row in place is not a tidiness problem — the service worker shows whatever
# arrives, so the first account's notifications would keep appearing on a browser somebody else is now
# signed in on. And the row cannot be reassigned through the new owner's own connection: the owner-match
# policy refuses an update it cannot see, so the subscribe would 500 and the stale row would survive.
#
# Scoped to one endpoint and driven by the caller having just presented it, which is the whole
# authorisation: a push endpoint is an unguessable capability URL minted by the browser, so possessing
# it is proof of controlling that browser.
async def release_endpoint(session: AsyncSession, endpoint: str, *, keep_user_id: int) -> None:
    await session.execute(sa_delete(PushSubscription).where(PushSubscription.endpoint == endpoint, PushSubscription.user_id != keep_user_id))


# Namespace to call repository functions (e.g. push_subscription_repository.list_by_user).
class PushSubscriptionRepository:
    list_by_user = staticmethod(list_by_user)
    list_by_user_ids = staticmethod(list_by_user_ids)
    upsert = staticmethod(upsert)
    touch = staticmethod(touch)
    delete_by_endpoint = staticmethod(delete_by_endpoint)
    release_endpoint = staticmethod(release_endpoint)


# Singleton used by services to access push-subscription persistence.
push_subscription_repository = PushSubscriptionRepository()
