from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Column, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.utils import utcnow


# What a notification is about.
#
# The values are money events today because money is what produces them, but nothing about the TABLES
# in this file is money-specific: an event is a name, its context travels in `payload`, and no column
# here is a foreign key to anything the money domain owns. That is the whole entity-agnostic
# requirement — a second module adds values to this enum and reuses every row, policy and preference
# below unchanged.
#
# Adding a value here is a MIGRATION, which the audit log's `entity_type`/`action` deliberately are
# not: those are VARCHARs so a second module needs no schema change, while this is bound as a Postgres
# enum (`SAEnum(..., name="notification_event")`) because a feed row's event decides which copy renders
# it and a typo must fail at the write rather than at the reader's screen. The list is ALSO transcribed
# in TypeScript (`apps/web/lib/constants/notifications.ts`), in `01_create_tables.sql` for a database
# built from zero, and in each migration's `ALTER TYPE … ADD VALUE` for one that got there
# incrementally — where the `BEFORE` clause matters, because ADD VALUE otherwise appends and the two
# paths end up holding the same labels in a different order.
# `tests/unit/test_notification_event_surface.py` asserts all four agree, order included.
#
# `obligation_due` and `plan_charged` are the only two that are PRIVATE — they are about one person's
# own subscriptions and bills, so their payload names no group and their link is not a group page.
class NotificationEvent(StrEnum):
    balance_written_off = "balance_written_off"
    group_invited = "group_invited"
    member_joined = "member_joined"
    obligation_due = "obligation_due"
    ownership_changed = "ownership_changed"
    plan_charged = "plan_charged"
    pot_movement = "pot_movement"
    settle_confirmed = "settle_confirmed"
    settle_marked_paid = "settle_marked_paid"
    shared_expense_added = "shared_expense_added"
    shared_income_added = "shared_income_added"
    snapshot_due = "snapshot_due"


# How a notification reaches someone. 'in_app' is the feed and is never sent anywhere; the other two
# leave the app and are therefore the ones a preference usually turns off.
class NotificationChannel(StrEnum):
    email = "email"
    in_app = "in_app"
    push = "push"


# One user's answer for one event on one channel, and ONLY when they have overridden the shipped
# default. Absence means "the default", which is why nothing is ever seeded: a new event needs no
# backfill, and a default that changes reaches everyone who never expressed an opinion about it.
# The defaults themselves live in app/domain/notification.py, in one table.
class NotificationPreference(SQLModel, table=True):
    __tablename__ = "notification_preferences"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Owner of the preference.")
    event: NotificationEvent = Field(sa_column=Column(SAEnum(NotificationEvent, name="notification_event"), nullable=False))
    channel: NotificationChannel = Field(sa_column=Column(SAEnum(NotificationChannel, name="notification_channel"), nullable=False))
    enabled: bool = Field(description="The user's explicit answer, which is the only reason this row exists.")
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


# One thing that happened, addressed to one person. Fanning an event out to five people writes five
# rows, because read state is per-person and a shared row could not carry it.
#
# `payload` holds every value the copy interpolates plus the ids a deep link is built from. It is
# rendered by the WEB from `notifications.<event>` translation keys — not stored as prose — so the feed
# re-reads in whatever language the reader is using now, and a copy fix reaches old rows. The email and
# push bodies are rendered by the API instead, for the same reason transactional emails are: there is
# no frontend renderer at send time.
#
# `digest_pending` is the whole queue behind the daily email digest, and it is a per-ROW fact rather
# than a per-user cursor for one reason: a cursor has to be initialised when somebody switches modes,
# and getting that wrong emails them a summary of six months of history. Set at dispatch, only for a
# recipient whose email is on for the event AND who asked for a daily summary; cleared by the digest
# job. A row that was never enqueued is never picked up however the user's setting later changes, and
# rows already enqueued still go out if they switch back — which is right, since the email was owed.
#
# `dedupe_key` is what makes a REPEATING notification safe to attempt on every tick. A partial unique
# index over (user_id, event, dedupe_key) turns the second attempt into a no-op, so the reminder job
# needs no "last notified" column anywhere and no state of its own — it just asks the database to
# refuse a duplicate. NULL means "no such rule", which is every one-off event, and two NULL keys never
# collide because NULLs are distinct in a unique index (the index's WHERE clause is about its size, not
# about that).
class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", description="Who this notification is for.")
    event: NotificationEvent = Field(sa_column=Column(SAEnum(NotificationEvent, name="notification_event"), nullable=False))
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        description="Values the copy interpolates and the ids its link is built from.",
    )
    dedupe_key: str | None = Field(
        default=None,
        max_length=255,
        description="Identifies a repeating notification so the same one is written at most once; NULL for a one-off.",
    )
    read_at: datetime | None = Field(default=None, description="When the recipient read it; NULL while unread.")
    digest_pending: bool = Field(default=False, description="True while this row still owes the recipient an email inside their daily digest.")
    created_at: datetime = Field(default_factory=utcnow)
