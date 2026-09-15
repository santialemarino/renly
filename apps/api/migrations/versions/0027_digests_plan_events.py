"""two private notification events, and the queue behind the daily email digest

Revision ID: 0027_digests_plan_events
Revises: 0026_shared_recon
Create Date: 2026-09-15

"""

import sqlalchemy as sa
from alembic import op

revision = "0027_digests_plan_events"
down_revision = "0026_shared_recon"
branch_labels = None
depends_on = None

# The partial index is what makes the hourly digest tick cheap: it holds only the rows that still owe
# somebody an email, which is a handful at any moment against a table that grows forever. Without it
# the job scans every notification ever written, every hour, to find nothing.
_PENDING_INDEX = "ix_notifications_digest_pending"


# Adds the two PRIVATE events and the digest queue.
#
# The enum values go in BEFORE 'group_invited' rather than at the end, which is where ADD VALUE would
# otherwise put them. `notification_event`'s declared order is the order the preferences grid presents
# (stated in 01_create_tables.sql and mirrored by the web's NOTIFICATION_EVENTS), and these two are the
# only events a user who belongs to no group can ever receive — so they lead. Matching the fresh-build
# order is also what keeps a migrated schema byte-identical to one built from the SQL script.
#
# Nothing in this migration READS the new labels, which matters: Postgres refuses to use an enum value
# added in the same transaction, and Alembic runs a migration inside one. A backfill referencing
# 'plan_charged' here would fail at runtime, not at review — so if one is ever needed it belongs in a
# separate revision.
def upgrade() -> None:
    op.execute("ALTER TYPE notification_event ADD VALUE IF NOT EXISTS 'obligation_due' BEFORE 'group_invited'")
    op.execute("ALTER TYPE notification_event ADD VALUE IF NOT EXISTS 'plan_charged' BEFORE 'group_invited'")

    # NOT NULL with a false default, so every row written before digests existed reads as "owes no
    # digest email" — which is exactly what it is. No backfill, and none possible to get wrong.
    op.add_column("notifications", sa.Column("digest_pending", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index(_PENDING_INDEX, "notifications", ["user_id"], postgresql_where=sa.text("digest_pending"))


# Drops the digest queue. The two enum values STAY declared, the same posture as 0009, 0012 and 0013:
# PostgreSQL cannot drop a value from an enum without recreating the type and rewriting every dependent
# column, and a declared value nothing writes is harmless.
#
# Down-migrating discards which rows still owed a digest email, so anybody on the daily cadence loses
# the queue for the period they were in. Every one of those rows is still in their feed — the digest
# only ever decided WHEN an email left, never whether the notification existed.
def downgrade() -> None:
    op.drop_index(_PENDING_INDEX, table_name="notifications")
    op.drop_column("notifications", "digest_pending")
