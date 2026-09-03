# Request/response schemas for the notification endpoints (HTTP contract).

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.models.notification import NotificationChannel, NotificationEvent
from app.schemas.base import RequestBase

# The longest push endpoint a request may carry: far above any real one (a few hundred bytes) and
# safely below 2704, the btree index key limit this bound exists to stay under.
PUSH_ENDPOINT_MAX_LENGTH = 2000


# Body for PUT /notifications/preferences. One switch at a time, which is what the grid emits: a whole
# matrix per save would make two people editing different rows overwrite each other's answers.
class NotificationPreferenceUpdate(RequestBase):
    event: NotificationEvent = Field(description="Which event the switch belongs to.")
    channel: NotificationChannel = Field(description="Which channel the switch belongs to.")
    enabled: bool = Field(description="Whether this event should reach the caller on this channel.")


# Body for POST /notifications/push/subscriptions. The three values come verbatim from the browser's
# PushSubscription — `keys.p256dh` and `keys.auth` are secrets and are never read back out.
class PushSubscriptionCreate(RequestBase):
    # Bounded at the REQUEST even though the column is unbounded TEXT, and the two are different
    # questions: the column stays TEXT because a third-party URL's shape is not ours to cap, while an
    # unbounded request body reaches a UNIQUE btree, whose key cannot exceed 2704 bytes. Without this a
    # long enough endpoint is `index row size N exceeds btree version 4 maximum 2704` — a 500 out of the
    # index rather than a 422 out of the contract (reproduced against a real Postgres, with
    # incompressible text: a repetitive 3 KB string fits, because the key is TOAST-compressed first).
    endpoint: str = Field(description="The push service URL the browser was issued.", max_length=PUSH_ENDPOINT_MAX_LENGTH)
    p256dh: str = Field(description="The browser's public key for payload encryption.", max_length=255)
    auth: str = Field(description="The browser's auth secret for payload encryption.", max_length=255)
    user_agent: str | None = Field(default=None, description="What the browser calls itself, to tell devices apart.", max_length=500)


# Body for DELETE /notifications/push/subscriptions. Named by endpoint rather than id because the
# browser knows its own endpoint and has never been told a database id.
class PushSubscriptionDelete(RequestBase):
    endpoint: str = Field(description="The push service URL to stop sending to.", max_length=PUSH_ENDPOINT_MAX_LENGTH)


# One notification in the feed.
#
# The row carries the event and its payload, never a rendered sentence: the client renders the prose
# from its own translations, so the feed reads in whatever language the reader is using now and a copy
# fix reaches rows written months ago. The payload also carries the ids the client builds the row's
# link from, so no route is stored.
class NotificationResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int = Field(description="Notification id.")
    event: NotificationEvent = Field(description="What happened.")
    payload: dict[str, Any] = Field(description="Values the copy interpolates and the ids its link is built from.")
    read_at: datetime | None = Field(default=None, description="When the caller read it; null while unread.")
    created_at: datetime = Field(description="When it happened.")


# Response for GET /notifications. `total` counts what the caller can actually see, so it agrees with
# the rows rather than with the table.
class NotificationFeedResponse(BaseModel):
    items: list[NotificationResponse] = Field(description="One page of notifications, newest first.")
    total: int = Field(description="How many notifications the caller has in total.")
    unread: int = Field(description="How many of them are unread.")


# Response for the two mark-read endpoints: how many rows actually changed, so a client can say nothing
# happened rather than claiming it did.
class NotificationReadResponse(BaseModel):
    updated: int = Field(description="How many notifications were marked read.")
    unread: int = Field(description="How many remain unread.")


# One cell of the preferences grid: the shipped default, and the caller's answer if they gave one.
class NotificationPreferenceResponse(BaseModel):
    event: NotificationEvent = Field(description="The event this switch belongs to.")
    channel: NotificationChannel = Field(description="The channel this switch belongs to.")
    enabled: bool = Field(description="Whether this event currently reaches the caller on this channel.")
    is_default: bool = Field(description="True while the caller has expressed no preference and the shipped default applies.")


# Response for GET /notifications/preferences: the full grid plus what this deployment can actually do.
#
# `push_available` is false when no VAPID key is configured, and the surface says so instead of offering
# a switch that would silently do nothing. `push_public_key` is the applicationServerKey the browser
# subscribes with — derived from the private key rather than configured beside it, so the pair cannot be
# mismatched.
class NotificationPreferencesResponse(BaseModel):
    preferences: list[NotificationPreferenceResponse] = Field(description="Every event on every channel, defaults included.")
    push_available: bool = Field(description="Whether this deployment can send web push at all.")
    push_public_key: str | None = Field(default=None, description="applicationServerKey for the browser; null when push is unavailable.")
    push_subscriptions: int = Field(description="How many browsers the caller currently has subscribed.")
