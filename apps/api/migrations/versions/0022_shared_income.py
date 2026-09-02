"""shared income: F1 inheritance and F2 destinations (the income half of the flow half)

Revision ID: 0022_shared_income
Revises: 0021_shared_expenses_settle
Create Date: 2026-09-02

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_shared_income"
down_revision = "0021_shared_expenses_settle"
branch_labels = None
depends_on = None

# Both tables this migration creates, in dependency order — used for the grants below and reversed for
# the drops, so the two halves cannot fall out of step with each other.
_TABLES = ("shared_income", "shared_income_splits")

# Read policy on shared_income. The membership branch is the visibility model; the EXISTS branch keeps
# a PRIVATE balance correct when a member leaves the group, exactly as shared_expenses' account branch
# does. Somebody's own account received the money, so the row is a movement in their own ledger —
# without the branch it vanishes from their balance query and the account silently loses money it
# really holds. There is no card branch, because income never arrives on a credit card.
_SHARED_INCOME_READ = """
CREATE POLICY shared_income_scope_read ON shared_income FOR SELECT
  USING (
    app_is_group_member(group_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id = shared_income.paid_to_account_id
        AND a.user_id = app_current_user_id()
    )
  )
"""


# Creates the income half of shared money: what a group earns together, how it divides, and where it
# lands.
#
# The shape worth knowing before reading the DDL is that shared_income_splits carries TWO figures per
# member — what they are entitled to (`amount`) and what actually reached them (`received_amount`) —
# and a member's balance is the difference summed over their splits. That makes the per-currency
# balances sum to zero by construction rather than by a rule, and it is the mirror of what
# shared_expense_splits does with `amount` and `paid_amount`: an entitlement is a claim on the group,
# while cash that has already arrived is the group having settled part of it.
#
# There is deliberately no receiver column, for exactly the reason there is no payer column on the
# expense side: money arriving in a SHARED account reaches the pot's owners in their own proportions,
# so no single member received it. Those proportions are PINNED onto the split rows at write time
# because the ownership ledger is replayable — derived on read, a back-dated ownership event would
# silently rewrite an old balance.
#
# `destination` and `paid_to_account_id` must agree (joint money lands in a pot's account, distributed
# money does not), and that rule is enforced in the service rather than by a CHECK: it depends on
# accounts.pot_id, and a CHECK cannot span two rows. Same reason transfers' same-scope invariant lives
# in the service.
def upgrade() -> None:
    destination = postgresql.ENUM("joint", "distributed", name="income_destination")
    destination.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "shared_income",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("category", postgresql.ENUM(name="income_category", create_type=False), nullable=True),
        sa.Column("split_method", postgresql.ENUM(name="split_method", create_type=False), nullable=False),
        sa.Column("destination", postgresql.ENUM(name="income_destination", create_type=False), nullable=False),
        # SET NULL rather than a delete guard: the source only labels the income and seeds its default
        # split, so losing the asset loses the label while the money stays recorded exactly as it was.
        sa.Column("source_investment_id", sa.BigInteger(), sa.ForeignKey("investments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paid_to_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("amount > 0", name="shared_income_positive_amount"),
        # Joint money is money in a pot, and a pot is worth what its holdings are worth — so joint
        # income with nowhere to land would claim every owner's share rose while no figure moved.
        # Whether the named account actually belongs to a pot of THIS group is the service's check;
        # this one only refuses the shape that is wrong whatever the account turns out to be.
        sa.CheckConstraint(
            "destination <> 'joint' OR paid_to_account_id IS NOT NULL",
            name="shared_income_joint_lands_somewhere",
        ),
    )
    op.create_index("idx_shared_income_group_date", "shared_income", ["group_id", sa.text("date DESC")])
    op.create_index(
        "idx_shared_income_account_date",
        "shared_income",
        ["paid_to_account_id", "date"],
        postgresql_where=sa.text("paid_to_account_id IS NOT NULL"),
    )
    # Partial, and it earns its place twice: the remembered per-source default reads this group's rows
    # by source, and moving an investment out of a pot has to find the income that named it.
    op.create_index(
        "idx_shared_income_source",
        "shared_income",
        ["source_investment_id"],
        postgresql_where=sa.text("source_investment_id IS NOT NULL"),
    )

    op.create_table(
        "shared_income_splits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shared_income_id", sa.BigInteger(), sa.ForeignKey("shared_income.id", ondelete="CASCADE"), nullable=False),
        # Denormalized from the parent for RLS, the way shared_expense_splits carries its own: a policy
        # that had to join shared_income would evaluate that join for every row of every query.
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("received_amount", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("shared_income_id", "member_id", name="shared_income_splits_member_once"),
        # A negative figure would let a split "un-earn" or "un-receive", inverting who owes whom while
        # still summing to the total.
        sa.CheckConstraint("amount >= 0 AND received_amount >= 0", name="shared_income_splits_nonnegative"),
    )
    op.create_index("idx_shared_income_splits_income", "shared_income_splits", ["shared_income_id"])
    op.create_index("idx_shared_income_splits_member", "shared_income_splits", ["member_id"])
    op.create_index("idx_shared_income_splits_group", "shared_income_splits", ["group_id"])

    for table in _TABLES:
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
        # 0003's ALTER DEFAULT PRIVILEGES should cover these, but grant explicitly — a lost GRANT is
        # invisible to a pg_dump comparison run with --no-privileges.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO renly_app")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO renly_app")

    # Both are group state, so membership is the gate — the same app_is_group_member() helper every
    # other group-scoped table uses, so no predicate is copy-pasted. The parent additionally gets a
    # second READ branch for rows naming an account the caller owns: without it, leaving a group would
    # silently take money off a member's own account that it really received. Reading is FOR SELECT and
    # writing FOR ALL on membership alone, because Postgres has no WITH CHECK for DELETE — one policy
    # carrying the wide branch would let a former member DELETE the group's income rather than merely
    # see the leg of it that reached their own account.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(_SHARED_INCOME_READ)
    op.execute(
        "CREATE POLICY shared_income_scope_write ON shared_income FOR ALL "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )
    # Splits get no second branch on purpose, matching shared_expense_splits: a split names no account
    # and moves no balance, so nothing goes silently wrong when it stops being visible. Leaving a group
    # removes its income from your /income list, which is what leaving already does, and it is visible
    # rather than silent.
    op.execute(
        "CREATE POLICY shared_income_splits_member_isolation ON shared_income_splits "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )


# Drops the income half entirely. Down-migrating discards every piece of shared income and every
# split — the balances they derive go with them, since nothing is stored as a running total. Nothing
# outside these two tables changes: no column was added elsewhere, so every private figure and every
# shared EXPENSE reads exactly as it did before.
# Dropped in reverse dependency order; the policies and triggers go with their tables.
def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
    postgresql.ENUM(name="income_destination").drop(op.get_bind(), checkfirst=True)
