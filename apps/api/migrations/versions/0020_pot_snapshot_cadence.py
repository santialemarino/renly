"""pot snapshot cadence — how often a co-owned pot is expected to be re-valued

Revision ID: 0020_pot_snapshot_cadence
Revises: 0019_pots_unit_ownership
Create Date: 2026-08-29

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_pot_snapshot_cadence"
down_revision = "0019_pots_unit_ownership"
branch_labels = None
depends_on = None


# Adds the cadence a pot declares for its own re-valuation. Deliberately left out of 0019 because PR
# 4 is its first reader — nothing before this migration could act on it.
#
# NOT NULL DEFAULT 'monthly', matching how `visibility` is shaped and for the same reason: a third
# "undeclared" state would mean exactly what 'ad_hoc' already means, and two spellings of one answer
# is how a freshness rule ends up with two branches that disagree. Monthly rather than weekly
# because monthly is the rhythm Renly itself keeps — auto-snapshots fire on the last day of the
# month, so a weekly default would mark every ticker-linked pot overdue on the day it is created,
# and an indicator that is always red is one nobody reads.
#
# The enum's ORDER is frequency-descending rather than alphabetical, matching how ownership_event_type
# orders by when an event can first occur: the SQL type is the one place the values have a natural
# sequence, and the Python StrEnum stays alphabetical like its siblings.
def upgrade() -> None:
    pot_cadence = postgresql.ENUM("weekly", "monthly", "ad_hoc", name="pot_cadence")
    pot_cadence.create(op.get_bind(), checkfirst=True)
    op.execute("ALTER TABLE pots ADD COLUMN snapshot_cadence pot_cadence NOT NULL DEFAULT 'monthly'")


# Drops the column and the type. Down-migrating discards each pot's declared cadence; nothing else
# reads it, so no derived figure changes — only the freshness expectation is forgotten.
def downgrade() -> None:
    op.drop_column("pots", "snapshot_cadence")
    postgresql.ENUM(name="pot_cadence").drop(op.get_bind(), checkfirst=True)
