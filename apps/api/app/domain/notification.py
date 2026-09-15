# What Renly notifies about by default, on which channel. Pure data plus one lookup — no database, no
# HTTP — so the shipped behaviour can be asserted directly rather than inferred from a service.
#
# Every event supports every channel: the matrix a user sees is a full events x channels grid, and a
# cell nobody can switch is a cell that has to be explained. What varies is only the DEFAULT.
#
# The rule behind the defaults, so a new event has an answer rather than a coin toss: in_app is on for
# everything (a feed interrupts nobody and costs a row), while email and push are on only for the
# events about the reader's OWN money or awaiting the reader's OWN action. Email and push share one
# default per event on purpose — two channels with different answers for the same event is two stories
# to explain about one thing.
#
# Absence of a preference row means the default, so changing a value here changes what everyone who
# never expressed an opinion receives. That is deliberate: the alternative is seeding rows per user per
# event, which turns every new event into a backfill and freezes yesterday's answer forever.

from enum import StrEnum

from app.models.notification import NotificationChannel, NotificationEvent

# Events whose email and push channels are ON out of the box.
#
#   * ownership_changed  — a re-agreement moves value between people; the only event here that can
#     change what you are worth without you doing anything.
#   * snapshot_due       — a periodic nudge is worthless if it only appears where you were not looking.
#   * settle_marked_paid — somebody says they paid you, and confirming it is your move.
#   * settle_confirmed   — your own payment being acknowledged closes the loop you opened.
#   * balance_written_off — somebody gave up a claim against you; it changes what you owe.
#   * obligation_due     — a bill you declared is coming up and nothing pays it for you, so it is
#     waiting on your own action; the same argument snapshot_due makes, and a reminder that only ever
#     appears in a feed you were not looking at is the one kind of reminder that cannot work.
#
# pot_movement is deliberately NOT here even though ownership_changed is, and the distinction is the
# reason units exist: a contribution dilutes everyone's PERCENTAGE and moves nobody's VALUE, whereas a
# re-agreement moves value between people. The rest (group_invited, member_joined,
# shared_expense_added, shared_income_added) are somebody else recording something — real activity,
# but a household recording ten expenses a week must not send ten emails to everyone in it.
#
# plan_charged is the sharpest case of that last rule and so is NOT here: it is about the reader's own
# money, which is the test the six above pass, but it awaits no action at all — Renly is recording a
# charge the reader configured to happen. Somebody with ten subscriptions would get ten emails and ten
# lock-screen interrupts a month for things going exactly to plan. It is also precisely the event the
# daily digest exists to make safe to turn on.
_OUTSIDE_APP_BY_DEFAULT = frozenset(
    {
        NotificationEvent.balance_written_off,
        NotificationEvent.obligation_due,
        NotificationEvent.ownership_changed,
        NotificationEvent.settle_confirmed,
        NotificationEvent.settle_marked_paid,
        NotificationEvent.snapshot_due,
    }
)


# How often Renly emails one person about the events they have email turned on for.
#
# A CADENCE rather than a channel, which is why it is not a fourth `NotificationChannel` value: the two
# would be mutually exclusive with nothing in the schema saying so. It is also per USER rather than per
# event — the thing somebody wants is "stop filling my inbox", not a per-event schedule — and it
# governs email alone. In-app needs no cadence (a feed is already a summary you read when you look) and
# push has none either (a batched lock-screen interrupt is a contradiction).
#
# Stored as a plain string in `user_settings.settings`, so a third value costs no migration.
class EmailCadence(StrEnum):
    daily = "daily"
    immediate = "immediate"


# What somebody gets before they express a preference: every email as it happens, which is what the app
# did before digests existed. A digest delays a message by up to a day, and nobody should have that
# applied to them without asking.
DEFAULT_EMAIL_CADENCE = EmailCadence.immediate


# Whether a channel is on for an event when the user has expressed no preference about it.
def is_enabled_by_default(event: NotificationEvent, channel: NotificationChannel) -> bool:
    if channel == NotificationChannel.in_app:
        return True
    return event in _OUTSIDE_APP_BY_DEFAULT
