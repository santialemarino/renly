"""shared expenses, splits, settle-up and the group's money settings (the flow half)

Revision ID: 0021_shared_expenses_settle
Revises: 0020_pot_snapshot_cadence
Create Date: 2026-08-29

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0021_shared_expenses_settle"
down_revision = "0020_pot_snapshot_cadence"
branch_labels = None
depends_on = None

# Every table this migration creates, in dependency order — used for the grants below and reversed
# for the drops, so the two halves cannot fall out of step with each other.
_TABLES = ("group_money_settings", "shared_expenses", "shared_expense_splits", "group_settlements")

# The three that carry a surrogate id, and therefore a sequence to grant. group_money_settings is
# keyed by group_id and has none.
_SEQUENCED = ("shared_expenses", "shared_expense_splits", "group_settlements")

# Read policy on shared_expenses. The membership branch is the visibility model; the two EXISTS
# branches keep a PRIVATE balance correct when a member leaves the group, exactly as
# pot_ownership_events' account branch does. A member's own account or card funded the row, so the
# row is a movement in their own ledger — without the branch it vanishes from their balance query
# and the account silently gains back money it no longer holds.
_SHARED_EXPENSES_READ = """
CREATE POLICY shared_expenses_scope_read ON shared_expenses FOR SELECT
  USING (
    app_is_group_member(group_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id = shared_expenses.paid_from_account_id
        AND a.user_id = app_current_user_id()
    )
    OR EXISTS (
      SELECT 1 FROM credit_cards c
      WHERE c.id = shared_expenses.credit_card_id
        AND c.user_id = app_current_user_id()
    )
  )
"""

_GROUP_SETTLEMENTS_READ = """
CREATE POLICY group_settlements_scope_read ON group_settlements FOR SELECT
  USING (
    app_is_group_member(group_id)
    OR EXISTS (
      SELECT 1 FROM accounts a
      WHERE a.id IN (group_settlements.from_account_id, group_settlements.to_account_id)
        AND a.user_id = app_current_user_id()
    )
  )
"""


# Creates the flow half of shared money: what a group spends together, how it divides, and how the
# resulting balances are cleared.
#
# The shape worth knowing before reading the DDL is that shared_expense_splits carries TWO figures per
# member — what they consumed (`amount`) and what they fronted (`paid_amount`) — and a member's balance
# is the difference summed over their splits. That makes the per-currency balances sum to zero by
# construction rather than by a rule, and it is what lets one implementation cover every case in the
# spec's §4.2 table, including money fronted by a SHARED account, where the pot's owners front it in
# their own proportions and no single member is the payer. Those proportions are PINNED here at write
# time because the ownership ledger is replayable: derived, a back-dated ownership event would silently
# rewrite an old balance.
#
# Group money settings land in a sibling table rather than as columns on `groups`, so the membership
# kernel keeps carrying who the people are and nothing about what they share.
def upgrade() -> None:
    split_method = postgresql.ENUM("equal", "exact", "shares", "percentage", name="split_method")
    split_method.create(op.get_bind(), checkfirst=True)
    # No 'reversed': reversing a settlement DELETES it, the same answer revoking a group invite got,
    # because until the audit log exists nothing would ever read a reversed state back.
    settlement_status = postgresql.ENUM("pending", "confirmed", "written_off", name="group_settlement_status")
    settlement_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "group_money_settings",
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
        sa.Column(
            "default_split_method",
            postgresql.ENUM(name="split_method", create_type=False),
            nullable=False,
            server_default="equal",
        ),
        sa.Column("auto_finalise_settlements", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    # Every group has exactly one settings row, so no read needs an "or the default" branch. Backfills
    # the groups that already exist; the service creates it alongside every new group from here on.
    op.execute("INSERT INTO group_money_settings (group_id) SELECT id FROM groups")

    op.create_table(
        "shared_expenses",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("category", postgresql.ENUM(name="expense_category", create_type=False), nullable=True),
        sa.Column("split_method", postgresql.ENUM(name="split_method", create_type=False), nullable=False),
        sa.Column("paid_from_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("payment_method", sa.String(length=20), nullable=True),
        # No ON DELETE, matching expense_entries.credit_card_id: a card carrying charges is refused by
        # the service with a real message rather than silently unlinking history.
        sa.Column("credit_card_id", sa.BigInteger(), sa.ForeignKey("credit_cards.id"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("amount > 0", name="shared_expenses_positive_amount"),
        # The cash leg and the card leg are exclusive — the same rule ensure_account_pairing enforces
        # on a private expense. Both set would draw an account AND raise a card bucket for one payment.
        sa.CheckConstraint(
            "paid_from_account_id IS NULL OR credit_card_id IS NULL",
            name="shared_expenses_single_funding",
        ),
    )
    op.create_index("idx_shared_expenses_group_date", "shared_expenses", ["group_id", sa.text("date DESC")])
    op.create_index(
        "idx_shared_expenses_account_date",
        "shared_expenses",
        ["paid_from_account_id", "date"],
        postgresql_where=sa.text("paid_from_account_id IS NOT NULL"),
    )
    op.create_index(
        "idx_shared_expenses_credit_card",
        "shared_expenses",
        ["credit_card_id"],
        postgresql_where=sa.text("credit_card_id IS NOT NULL"),
    )

    op.create_table(
        "shared_expense_splits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("shared_expense_id", sa.BigInteger(), sa.ForeignKey("shared_expenses.id", ondelete="CASCADE"), nullable=False),
        # Denormalized from the parent for RLS, the way the scoped stock tables carry theirs: a policy
        # that had to join shared_expenses would evaluate that join for every row of every query.
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("paid_amount", sa.Numeric(18, 2), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("shared_expense_id", "member_id", name="shared_expense_splits_member_once"),
        # A negative figure would let a split "un-consume" or "un-pay", inverting who owes whom while
        # still summing to the total.
        sa.CheckConstraint("amount >= 0 AND paid_amount >= 0", name="shared_expense_splits_nonnegative"),
    )
    op.create_index("idx_shared_expense_splits_expense", "shared_expense_splits", ["shared_expense_id"])
    op.create_index("idx_shared_expense_splits_member", "shared_expense_splits", ["member_id"])
    op.create_index("idx_shared_expense_splits_group", "shared_expense_splits", ["group_id"])

    op.create_table(
        "group_settlements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("to_member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="group_settlement_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("from_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("from_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("to_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("amount > 0", name="group_settlements_positive_amount"),
        sa.CheckConstraint("from_member_id <> to_member_id", name="group_settlements_distinct_members"),
        sa.CheckConstraint(
            "(from_amount IS NULL OR from_amount > 0) AND (to_amount IS NULL OR to_amount > 0)",
            name="group_settlements_positive_legs",
        ),
        sa.CheckConstraint(
            "from_account_id IS NULL OR to_account_id IS NULL OR from_account_id <> to_account_id",
            name="group_settlements_distinct_accounts",
        ),
        # A write-off gave up on a debt; no cash moved, so an account leg would record a movement that
        # never happened. Safe against the ON DELETE SET NULL above — clearing an account id only makes
        # this MORE satisfied. The mirror rule ("a leg amount requires its account") is deliberately NOT
        # a CHECK: 0016 measured that shape to make any account that ever funded a cross-currency
        # settlement permanently undeletable, so the service enforces it on write instead.
        sa.CheckConstraint(
            "status <> 'written_off' OR (from_account_id IS NULL AND to_account_id IS NULL)",
            name="group_settlements_write_off_moves_nothing",
        ),
        sa.CheckConstraint(
            "(status = 'confirmed') = (confirmed_at IS NOT NULL)",
            name="group_settlements_confirmed_at",
        ),
    )
    op.create_index("idx_group_settlements_group_date", "group_settlements", ["group_id", sa.text("date DESC")])
    op.create_index("idx_group_settlements_from_member", "group_settlements", ["from_member_id"])
    op.create_index("idx_group_settlements_to_member", "group_settlements", ["to_member_id"])
    op.create_index(
        "idx_group_settlements_from_account_date",
        "group_settlements",
        ["from_account_id", "date"],
        postgresql_where=sa.text("from_account_id IS NOT NULL"),
    )
    op.create_index(
        "idx_group_settlements_to_account_date",
        "group_settlements",
        ["to_account_id", "date"],
        postgresql_where=sa.text("to_account_id IS NOT NULL"),
    )

    for table in _TABLES:
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
        # 0003's ALTER DEFAULT PRIVILEGES should cover these, but grant explicitly — a lost GRANT is
        # invisible to a pg_dump comparison run with --no-privileges.
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO renly_app")
    for table in _SEQUENCED:
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO renly_app")

    # All four are group state, so membership is the gate — the same app_is_group_member() helper the
    # membership and invite tables use, so no predicate is copy-pasted and `role` appears in none of
    # them. Two of the four additionally get a second READ branch for rows naming an account or card the
    # caller owns: without it, leaving a group would silently give a member's own account back money it
    # no longer holds. Reading is FOR SELECT and writing FOR ALL on membership alone, because Postgres
    # has no WITH CHECK for DELETE — one policy carrying the wide branch would let a former member
    # DELETE the group's expense rather than merely see their own leg of it.
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY group_money_settings_member_isolation ON group_money_settings "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )
    op.execute(_SHARED_EXPENSES_READ)
    op.execute(
        "CREATE POLICY shared_expenses_scope_write ON shared_expenses FOR ALL "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )
    # Splits get no second branch on purpose: a split names no account and moves no balance, so nothing
    # goes silently wrong when it stops being visible. Leaving a group removes its expenses from your
    # /expenses list, which is what leaving already does to a pot, and it is visible rather than silent.
    op.execute(
        "CREATE POLICY shared_expense_splits_member_isolation ON shared_expense_splits "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )
    op.execute(_GROUP_SETTLEMENTS_READ)
    op.execute(
        "CREATE POLICY group_settlements_scope_write ON group_settlements FOR ALL "
        "USING (app_is_group_member(group_id)) WITH CHECK (app_is_group_member(group_id))"
    )


# Drops the flow half entirely. Down-migrating discards every shared expense, every split and every
# recorded settlement — the balances they derive go with them, since nothing is stored as a running
# total. Nothing outside these four tables changes: no column was added elsewhere, so every private
# figure reads exactly as it did before.
# Dropped in reverse dependency order; the policies and triggers go with their tables.
def downgrade() -> None:
    for table in reversed(_TABLES):
        op.drop_table(table)
    postgresql.ENUM(name="group_settlement_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="split_method").drop(op.get_bind(), checkfirst=True)
