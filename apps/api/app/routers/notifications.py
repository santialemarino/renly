from fastapi import APIRouter, Query, status

from app.deps.auth import CurrentUser
from app.deps.db import SessionDep
from app.schemas.notification import (
    NotificationFeedResponse,
    NotificationPreferencesResponse,
    NotificationPreferenceUpdate,
    NotificationReadResponse,
    PushSubscriptionCreate,
    PushSubscriptionDelete,
)
from app.services import notification_service

router = APIRouter(prefix="/notifications", tags=["notifications"])

# What the feed returns when a caller does not ask. The bell popover asks for fewer; the page asks for
# more, up to the service's own cap.
DEFAULT_FEED_PAGE_SIZE = 20


# Returns one page of the caller's notifications, newest first, with the total and the unread count.
@router.get("", response_model=NotificationFeedResponse)
async def get_feed(
    current_user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=DEFAULT_FEED_PAGE_SIZE, ge=1, le=notification_service.MAX_FEED_PAGE_SIZE, description="Rows per page."),
    offset: int = Query(default=0, ge=0, description="Rows to skip."),
) -> NotificationFeedResponse:
    return await notification_service.get_feed(session, current_user, limit=limit, offset=offset)


# Marks one notification read. Returns 404 for an id that is not the caller's.
@router.post("/{notification_id}/read", response_model=NotificationReadResponse)
async def mark_read(notification_id: int, current_user: CurrentUser, session: SessionDep) -> NotificationReadResponse:
    return await notification_service.mark_read(session, notification_id, current_user)


# Marks every notification the caller can see read.
@router.post("/read-all", response_model=NotificationReadResponse)
async def mark_all_read(current_user: CurrentUser, session: SessionDep) -> NotificationReadResponse:
    return await notification_service.mark_all_read(session, current_user)


# Returns the full preferences grid (every event on every channel) plus whether this deployment can
# send web push and the key a browser subscribes with.
@router.get("/preferences", response_model=NotificationPreferencesResponse)
async def get_preferences(current_user: CurrentUser, session: SessionDep) -> NotificationPreferencesResponse:
    return await notification_service.get_preferences(session, current_user)


# Sets one switch and returns the whole grid, so a client re-renders from one source.
@router.put("/preferences", response_model=NotificationPreferencesResponse)
async def set_preference(body: NotificationPreferenceUpdate, current_user: CurrentUser, session: SessionDep) -> NotificationPreferencesResponse:
    return await notification_service.set_preference(session, current_user, event=body.event, channel=body.channel, enabled=body.enabled)


# Registers the calling browser for web push, or refreshes the keys of one already registered. Returns
# 409 (`push_not_configured`) on a deployment with no VAPID key.
@router.post("/push/subscriptions", response_model=NotificationPreferencesResponse, status_code=status.HTTP_201_CREATED)
async def subscribe_push(body: PushSubscriptionCreate, current_user: CurrentUser, session: SessionDep) -> NotificationPreferencesResponse:
    return await notification_service.subscribe_push(
        session, current_user, endpoint=body.endpoint, p256dh=body.p256dh, auth=body.auth, user_agent=body.user_agent
    )


# Stops sending push to one browser, named by its own endpoint. Idempotent.
# The endpoint travels in the BODY rather than a query parameter: it identifies one person's browser,
# and a URL is the one part of a request that reliably ends up in an access log.
@router.delete("/push/subscriptions", response_model=NotificationPreferencesResponse)
async def unsubscribe_push(body: PushSubscriptionDelete, current_user: CurrentUser, session: SessionDep) -> NotificationPreferencesResponse:
    return await notification_service.unsubscribe_push(session, current_user, endpoint=body.endpoint)
