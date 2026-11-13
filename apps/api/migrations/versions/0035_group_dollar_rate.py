"""group dollar rate — the USD/ARS quote a group settles up at

Revision ID: 0035_group_dollar_rate
Revises: 0034_pot_dollar_rate
Create Date: 2026-11-12

"""

from alembic import op

revision = "0035_group_dollar_rate"
down_revision = "0034_pot_dollar_rate"
branch_labels = None
depends_on = None


# Adds the dollar rate a group settles at. Until now a payment in one currency cleared debt in another at
# the PAYER's own preference, and the "at today's rate" figure beside a balance used each reader's, so
# two members could disagree about what one payment had cleared.
#
# NOT NULL DEFAULT 'mep', matching the app's own default preference and a pot's, so every group that
# already exists settles at one well-defined rate from the moment this lands. Recorded settlements are
# untouched: each stores the amounts it cleared, and those are never recomputed.
#
# Changing it afterwards takes every active member's agreement, so the row also carries at most ONE
# pending proposal — the same three columns and CHECK a pot's rate has (0034).
#
# The members hear about each step — proposed, applied, withdrawn — through a notification event of its
# own, `settle_rate_changed`, declared BEFORE 'shared_expense_added' — right after 'balance_written_off' — so it sits with the other settling-up
# events in the preferences grid, matching the fresh-build order in 01_create_tables.sql. Declaring a
# value is safe inside Alembic's transaction on PostgreSQL 12+ because nothing writes a row using it here.
def upgrade() -> None:
    op.execute("ALTER TYPE notification_event ADD VALUE IF NOT EXISTS 'settle_rate_changed' BEFORE 'shared_expense_added'")
    op.execute("ALTER TABLE group_money_settings ADD COLUMN dollar_rate dollar_rate NOT NULL DEFAULT 'mep'")
    op.execute("ALTER TABLE group_money_settings ADD COLUMN dollar_rate_proposal dollar_rate")
    op.execute("ALTER TABLE group_money_settings ADD COLUMN dollar_rate_proposed_by BIGINT REFERENCES group_members(id)")
    op.execute("ALTER TABLE group_money_settings ADD COLUMN dollar_rate_agreed_by BIGINT[] NOT NULL DEFAULT '{}'")
    op.execute(
        "ALTER TABLE group_money_settings ADD CONSTRAINT group_money_settings_dollar_rate_proposal_whole "
        "CHECK ((dollar_rate_proposal IS NULL) = (dollar_rate_proposed_by IS NULL))"
    )


# Drops the columns. Settling up converts at the payer's own preference again and a pending proposal is
# forgotten; no stored figure changes, because no settlement ever depended on them. The `dollar_rate`
# type stays: pots still use it. So does the 'settle_rate_changed' event value, the posture 0009, 0012,
# 0013 and 0027 take: PostgreSQL cannot drop a value from an enum without recreating the type and
# rewriting every dependent column, and a declared value nothing writes is harmless.
def downgrade() -> None:
    op.execute("ALTER TABLE group_money_settings DROP CONSTRAINT group_money_settings_dollar_rate_proposal_whole")
    op.execute("ALTER TABLE group_money_settings DROP COLUMN dollar_rate_agreed_by")
    op.execute("ALTER TABLE group_money_settings DROP COLUMN dollar_rate_proposed_by")
    op.execute("ALTER TABLE group_money_settings DROP COLUMN dollar_rate_proposal")
    op.execute("ALTER TABLE group_money_settings DROP COLUMN dollar_rate")
