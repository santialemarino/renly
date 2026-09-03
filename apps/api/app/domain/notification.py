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

from app.models.notification import NotificationChannel, NotificationEvent

# Events whose email and push channels are ON out of the box.
#
#   * ownership_changed  — a re-agreement moves value between people; the only event here that can
#     change what you are worth without you doing anything.
#   * snapshot_due       — a periodic nudge is worthless if it only appears where you were not looking.
#   * settle_marked_paid — somebody says they paid you, and confirming it is your move.
#   * settle_confirmed   — your own payment being acknowledged closes the loop you opened.
#   * balance_written_off — somebody gave up a claim against you; it changes what you owe.
#
# pot_movement is deliberately NOT here even though ownership_changed is, and the distinction is the
# reason units exist: a contribution dilutes everyone's PERCENTAGE and moves nobody's VALUE, whereas a
# re-agreement moves value between people. The rest (group_invited, member_joined,
# shared_expense_added, shared_income_added) are somebody else recording something — real activity,
# but a household recording ten expenses a week must not send ten emails to everyone in it.
_OUTSIDE_APP_BY_DEFAULT = frozenset(
    {
        NotificationEvent.balance_written_off,
        NotificationEvent.ownership_changed,
        NotificationEvent.settle_confirmed,
        NotificationEvent.settle_marked_paid,
        NotificationEvent.snapshot_due,
    }
)


# Whether a channel is on for an event when the user has expressed no preference about it.
def is_enabled_by_default(event: NotificationEvent, channel: NotificationChannel) -> bool:
    if channel == NotificationChannel.in_app:
        return True
    return event in _OUTSIDE_APP_BY_DEFAULT
