"""pot dollar rate — the USD/ARS quote every member of a pot values it at

Revision ID: 0034_pot_dollar_rate
Revises: 0033_transfer_follows_accounts
Create Date: 2026-11-09

"""

from alembic import op

revision = "0034_pot_dollar_rate"
down_revision = "0033_transfer_follows_accounts"
branch_labels = None
depends_on = None


# Adds the dollar rate a pot converts at. Until now a pot's value, unit price and every movement priced
# against it converted with the CALLER's own preference, so two members with different preferences saw
# different figures and units were issued at whichever rate the contributor happened to prefer.
#
# NOT NULL DEFAULT 'mep', matching the app's own default preference, so every pot that already exists
# keeps one well-defined rate from the moment this lands. Recorded ledger rows are untouched: each
# already stores its base_amount and units, and those are never recomputed.
#
# Changing it afterwards takes every owner's agreement, so the pot also carries at most ONE pending
# proposal: the rate proposed, the seat that proposed it, and the seats that have agreed so far. On the
# pot rather than in a table of its own because there is never more than one, it is read on every pot
# response, and the pot's own row-level policies already say who may see and change it. The CHECK keeps a
# proposal whole: a rate with no proposer, or a proposer with no rate, is not a state anything reads.
def upgrade() -> None:
    op.execute("CREATE TYPE dollar_rate AS ENUM ('oficial', 'mep', 'blue')")
    op.execute("ALTER TABLE pots ADD COLUMN dollar_rate dollar_rate NOT NULL DEFAULT 'mep'")
    op.execute("ALTER TABLE pots ADD COLUMN dollar_rate_proposal dollar_rate")
    op.execute("ALTER TABLE pots ADD COLUMN dollar_rate_proposed_by BIGINT REFERENCES group_members(id)")
    op.execute("ALTER TABLE pots ADD COLUMN dollar_rate_agreed_by BIGINT[] NOT NULL DEFAULT '{}'")
    op.execute(
        "ALTER TABLE pots ADD CONSTRAINT pots_dollar_rate_proposal_whole "
        "CHECK ((dollar_rate_proposal IS NULL) = (dollar_rate_proposed_by IS NULL))"
    )


# Drops the columns and the type. Every pot then converts with each reader's own preference again, and
# a pending proposal is forgotten; no stored figure changes, because no ledger row ever depended on them.
def downgrade() -> None:
    op.execute("ALTER TABLE pots DROP CONSTRAINT pots_dollar_rate_proposal_whole")
    op.execute("ALTER TABLE pots DROP COLUMN dollar_rate_agreed_by")
    op.execute("ALTER TABLE pots DROP COLUMN dollar_rate_proposed_by")
    op.execute("ALTER TABLE pots DROP COLUMN dollar_rate_proposal")
    op.execute("ALTER TABLE pots DROP COLUMN dollar_rate")
    op.execute("DROP TYPE dollar_rate")
