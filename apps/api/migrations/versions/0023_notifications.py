"""notification layer: events x channels x preferences, in-app feed and web push subscriptions

Revision ID: 0023_notifications
Revises: 0022_shared_income
Create Date: 2026-09-02

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0023_notifications"
down_revision = "0022_shared_income"
branch_labels = None
depends_on = None

# Every table this migration creates, in dependency order — used for the triggers and grants below and
# reversed for the drops, so the two halves cannot fall out of step with each other. There is no
# dependency BETWEEN them: all three hang off users and nothing else, which is what makes the layer
# reusable by a module that knows nothing about money.
_TABLES = ("notification_preferences", "notifications", "push_subscriptions")

# Tables whose updated_at is maintained by the shared trigger. notifications and push_subscriptions
# have none on purpose: a notification is an immutable record of something that happened (only read_at
# ever changes, and its own value is the timestamp), and a subscription's mutable field is
# last_used_at, which the sender sets explicitly because "when did a send last succeed" is not the same
# question as "when was this row last touched".
_TABLES_WITH_UPDATED_AT = ("notification_preferences",)

# The event enum's labels, in the order the surface presents them rather than alphabetically, matching
# how income_destination and group_settlement_status are declared. The values are money events because
# shared money is what produces them; the TABLES below name no money entity, which is the property that
# lets a second module add labels here and reuse everything else unchanged.
_EVENTS = (
    "group_invited",
    "member_joined",
    "ownership_changed",
    "pot_movement",
    "snapshot_due",
    "settle_marked_paid",
    "settle_confirmed",
    "balance_written_off",
    "shared_expense_added",
    "shared_income_added",
)

_CHANNELS = ("in_app", "email", "push")

# Reading, marking read and deleting are the caller's own rows. INSERT gets NO policy at all, and that
# is the design rather than an omission: fanning an event out writes rows for OTHER users, which a
# user_id = app_current_user_id() WITH CHECK could never permit, so the dispatcher runs on the
# privileged session exactly as group creation and invite acceptance do. With RLS enabled and no INSERT
# policy, the request role cannot write a notification at all — nobody can forge an entry in their own
# feed, or anyone else's, through any request path.
#
# UPDATE carries WITH CHECK as well as USING, so marking one read cannot also re-address it to somebody
# else. It is genuinely defence in depth rather than the only guard: Postgres additionally requires an
# updated row to remain visible under the SELECT policy, so widening EITHER one alone still refuses the
# re-address, and both have to go for it to become possible (proven by mutating each in turn). Keeping
# the WITH CHECK means integrity here does not depend on the confidentiality policy staying narrow.
# DELETE has no WITH CHECK in Postgres, hence its own policy rather than a FOR ALL that would have
# needed one.
_NOTIFICATION_POLICIES = (
    "CREATE POLICY notifications_user_read ON notifications FOR SELECT USING (user_id = app_current_user_id())",
    "CREATE POLICY notifications_user_update ON notifications FOR UPDATE "
    "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())",
    "CREATE POLICY notifications_user_delete ON notifications FOR DELETE USING (user_id = app_current_user_id())",
)


# Creates the notification layer: what a person has asked to be told about, what they have been told,
# and which browsers have agreed to receive a push.
#
# All three tables are USER-owned, not group-scoped, so they take the plain owner-match policy shape
# and never call app_is_group_member(): a notification belongs to its recipient, not to the group whose
# activity produced it. That is also why the fan-out decides recipients in the service — the group's
# visibility rules choose WHO gets a row, and once written the row is simply that person's.
#
# notification_preferences stores only OVERRIDES. There is no seeding step and no backfill for a future
# event: a missing row means the shipped default (app/domain/notification.py), so a new event has an
# answer on the day it is added, for every existing account.
#
# The partial unique index on notifications is what makes a REPEATING notification idempotent. The
# overdue-valuation reminder is attempted hourly; it carries a dedupe key naming the pot and the cadence
# period, and this index turns every attempt after the first into a no-op. That deliberately replaces a
# "last notified" column — one would have to live on pots (a per-pot answer to a per-user question) and
# would need its own reset rule when the period rolls over, which the key encodes for free.
def upgrade() -> None:
    event = postgresql.ENUM(*_EVENTS, name="notification_event")
    event.create(op.get_bind(), checkfirst=True)
    channel = postgresql.ENUM(*_CHANNELS, name="notification_channel")
    channel.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", postgresql.ENUM(name="notification_event", create_type=False), nullable=False),
        sa.Column("channel", postgresql.ENUM(name="notification_channel", create_type=False), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        # One answer per person per event per channel. A second row would be a second opinion about the
        # same switch, and the reader would have to pick one.
        sa.UniqueConstraint("user_id", "event", "channel", name="notification_preferences_once"),
    )
    # The read is always "every override this user holds", so the unique constraint's index already
    # serves it on its leading column and a second index on user_id alone would be dead weight.

    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event", postgresql.ENUM(name="notification_event", create_type=False), nullable=False),
        # The values the copy interpolates and the ids its link is built from. JSONB rather than columns
        # precisely because the layer must not know what a pot is: every event carries its own shape.
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("dedupe_key", sa.String(length=255), nullable=True),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    # The feed is one user's rows newest first, which is the only way this table is ever read.
    op.create_index("idx_notifications_user_created", "notifications", ["user_id", sa.text("created_at DESC")])
    # The unread badge counts a user's unread rows, and the partial index is the whole point: a feed is
    # mostly read, so this stays small however long the history grows.
    op.create_index(
        "idx_notifications_user_unread",
        "notifications",
        ["user_id"],
        postgresql_where=sa.text("read_at IS NULL"),
    )
    # PARTIAL unique. The WHERE clause is about SIZE, not semantics: NULLs are distinct in a unique
    # index, so two keyless rows would not collide either way (checked, rather than assumed) — this
    # keeps the index to the rows that opt in, on a table that is mostly one-off notifications.
    # It does have one consequence the repository has to honour: an ON CONFLICT naming these three
    # columns must repeat this predicate, or Postgres answers "no unique or exclusion constraint
    # matching the ON CONFLICT specification" and the whole insert raises. Since dispatch swallows its
    # own exceptions, that failure would be every notification silently vanishing — so the arbiter is
    # driven against a real database in tests/integration/test_notification_queries.py.
    op.create_index(
        "idx_notifications_dedupe",
        "notifications",
        ["user_id", "event", "dedupe_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_key IS NOT NULL"),
    )

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        # Globally unique, not unique per user: the push service mints one endpoint per browser, so the
        # same endpoint arriving again is the same browser re-subscribing — an upsert, never a duplicate.
        # Unbounded length because the endpoint is a third-party URL whose shape is not ours to cap.
        sa.Column("endpoint", sa.Text(), nullable=False),
        # SECRETS. Anyone holding these two plus the endpoint can push to that browser as if they were
        # Renly, so they are never logged, never returned by an endpoint, and never exported.
        sa.Column("p256dh", sa.String(length=255), nullable=False),
        sa.Column("auth", sa.String(length=255), nullable=False),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("endpoint", name="push_subscriptions_endpoint_once"),
    )
    op.create_index("idx_push_subscriptions_user", "push_subscriptions", ["user_id"])

    for table in _TABLES_WITH_UPDATED_AT:
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
    for table in _TABLES:
        # 0003's ALTER DEFAULT PRIVILEGES should cover these, but grant explicitly — a lost GRANT is
        # invisible to a pg_dump comparison run with --no-privileges.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO renly_app")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO renly_app")
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")

    # Preferences and subscriptions are wholly the user's own to write, so each gets the plain
    # owner-match FOR ALL policy every other user-owned table in this schema carries.
    op.execute(
        "CREATE POLICY notification_preferences_user_isolation ON notification_preferences "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )
    op.execute(
        "CREATE POLICY push_subscriptions_user_isolation ON push_subscriptions "
        "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
    )
    for policy in _NOTIFICATION_POLICIES:
        op.execute(policy)


# Drops the notification layer entirely. Down-migrating discards every stored notification, every
# preference override (so everyone reverts to the shipped defaults) and every push subscription — a
# browser that had agreed to receive push simply stops receiving it, and re-subscribing after a
# re-upgrade is one click. Nothing outside these three tables changes: no column was added elsewhere,
# so every figure in the app reads exactly as it did before.
# Dropped in reverse dependency order; the policies, indexes and triggers go with their tables.
def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
    postgresql.ENUM(name="notification_channel").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="notification_event").drop(op.get_bind(), checkfirst=True)
