"""pots, unit ownership and scope on the stock tables — shared money's destructive change

Revision ID: 0019_pots_unit_ownership
Revises: 0018_groups_membership
Create Date: 2026-08-25

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0019_pots_unit_ownership"
down_revision = "0018_groups_membership"
branch_labels = None
depends_on = None

# The tables that gain a scope: their user_id stops meaning "the account that typed this in" and
# starts meaning "the owner", which is NULL exactly when the row belongs to a pot instead.
_SCOPED_TABLES = (
    "investments",
    "investment_snapshots",
    "transactions",
    "accounts",
    "account_reconciliations",
    "transfers",
)

# Only the two parents carry authorship; the four children denormalize scope alone, which is all
# their RLS policy reads and all it has ever read.
_AUTHORED_TABLES = ("investments", "accounts")

# The index name for a table's pot_id, mirroring 0003's idx_snapshots_user_id abbreviation so the two
# scope indexes on a table read as a pair rather than as two unrelated names.
_POT_INDEX = {
    "investments": "idx_investments_pot_id",
    "investment_snapshots": "idx_snapshots_pot_id",
    "transactions": "idx_transactions_pot_id",
    "accounts": "idx_accounts_pot_id",
    "account_reconciliations": "idx_account_reconciliations_pot_id",
    "transfers": "idx_transfers_pot_id",
}

# The owner-match policy each scoped table carried before this migration, recreated verbatim by
# downgrade(). Written out rather than generated because a downgrade has to restore what the EARLIER
# migrations actually created (0003, 0010, 0012, 0014), and those are fixed text, not a pattern this
# migration is free to reinterpret.
_LEGACY_POLICY = {
    "investments": "investments_user_isolation",
    "investment_snapshots": "investment_snapshots_user_isolation",
    "transactions": "transactions_user_isolation",
    "accounts": "accounts_user_isolation",
    "account_reconciliations": "account_reconciliations_user_isolation",
    "transfers": "transfers_user_isolation",
}

# Kept byte-identical to the copies in database/01_create_tables.sql, indentation included: pg_dump
# reproduces a function body verbatim, so differently-indented copies make a migrated database and a
# fresh one differ textually even though they behave the same. Hence the unindented literals — and
# tests/unit/test_schema_parity.py asserts they still match the schema file, which is the guard the
# 0018 build record described but never actually added.
_APP_CAN_VIEW_POT_SQL = """
CREATE OR REPLACE FUNCTION app_can_view_pot(p_pot_id BIGINT) RETURNS BOOLEAN
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    SELECT EXISTS (
      SELECT 1 FROM pots p
      JOIN group_members gm ON gm.group_id = p.group_id
      LEFT JOIN pot_member_permissions pmp ON pmp.pot_id = p.id AND pmp.member_id = gm.id
      WHERE p.id = p_pot_id
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
        AND COALESCE(pmp.can_view, p.visibility = 'members')
    )
  $$
"""

_APP_CAN_WRITE_POT_SQL = """
CREATE OR REPLACE FUNCTION app_can_write_pot(p_pot_id BIGINT) RETURNS BOOLEAN
  LANGUAGE sql STABLE SECURITY DEFINER
  SET search_path = public, pg_temp
  AS $$
    SELECT EXISTS (
      SELECT 1 FROM pots p
      JOIN group_members gm ON gm.group_id = p.group_id
      JOIN pot_member_permissions pmp ON pmp.pot_id = p.id AND pmp.member_id = gm.id
      WHERE p.id = p_pot_id
        AND gm.user_id = app_current_user_id()
        AND gm.is_active
        AND pmp.can_write
    )
  $$
"""

_VIEW = "app_can_view_pot(pot_id)"
_WRITE = "app_can_write_pot(pot_id)"


# Builds the pair of dual-scope policies for one table. TWO policies rather than one, and the split
# is not stylistic: Postgres applies WITH CHECK to the new row on INSERT/UPDATE but has NO WITH CHECK
# for DELETE, so a single FOR ALL policy whose USING named app_can_view_pot would let a read-only
# member delete a shared holding. Permissive policies are OR-ed, so SELECT still resolves to the view
# predicate (can_write implies can_view by CHECK, so the union adds nothing).
def _scope_policies(table: str) -> tuple[str, str]:
    owner = "user_id = app_current_user_id()"
    read = f"CREATE POLICY {table}_scope_read ON {table} FOR SELECT USING ({owner} OR (pot_id IS NOT NULL AND {_VIEW}))"
    write = (
        f"CREATE POLICY {table}_scope_write ON {table} FOR ALL "
        f"USING ({owner} OR (pot_id IS NOT NULL AND {_WRITE})) "
        f"WITH CHECK ({owner} OR (pot_id IS NOT NULL AND {_WRITE}))"
    )
    return (read, write)


# Adds the pot container, its permissions and its ownership ledger, then re-points the stock tables'
# user_id from AUTHOR to OWNER. That last part is the destructive change the pre-launch window exists
# for: after this revision a holding belongs either to a user or to a pot, never to both, and
# `user_id = me` means "exactly my private holdings" by construction rather than by convention.
#
# The ordering is load-bearing in one place only — created_by is backfilled from user_id while
# user_id is still the author, which it is for every row that exists at this revision (nothing could
# have created a shared holding yet). Everything else is independent.
def upgrade() -> None:
    pot_visibility = postgresql.ENUM("members", "owners", name="pot_visibility")
    pot_visibility.create(op.get_bind(), checkfirst=True)
    ownership_event_type = postgresql.ENUM(
        "opening", "contribution", "withdrawal", "reagreement", name="ownership_event_type"
    )
    ownership_event_type.create(op.get_bind(), checkfirst=True)

    # Ownership lives on the pot and never on the holding: a rebalance inside the pot (sell A, buy B)
    # would otherwise have to move ownership units between positions, which is meaningless and a
    # silent source of wrong percentages. name is NULL for a group's default pot — the container is a
    # concept the UI does not surface until a group has a second one to distinguish it from.
    op.create_table(
        "pots",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("group_id", sa.BigInteger(), sa.ForeignKey("groups.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("base_currency", sa.String(length=3), nullable=False),
        sa.Column("visibility", postgresql.ENUM(name="pot_visibility", create_type=False), nullable=False, server_default="members"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("idx_pots_group_id", "pots", ["group_id"])
    op.create_index("idx_pots_group_default", "pots", ["group_id"], unique=True, postgresql_where=sa.text("is_default"))

    # Per-member overrides of the pot's visibility default, and the ONLY source of write access.
    # Membership is not ownership: a member holding 0% may still see all of it, so can_view is keyed
    # to the seat and never to whether the member holds units. The CHECK makes can_write imply
    # can_view, which is what keeps app_can_write_pot from ever answering true where the view helper
    # answers false.
    op.create_table(
        "pot_member_permissions",
        sa.Column("pot_id", sa.BigInteger(), sa.ForeignKey("pots.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("can_view", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("can_write", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint("can_view OR NOT can_write", name="pot_member_permissions_write_implies_view"),
    )
    op.create_index("idx_pot_member_permissions_member_id", "pot_member_permissions", ["member_id"])

    # The ownership ledger: dated events REPLAYED to derive unit balances, with nothing stored as a
    # running total — the same posture as every other balance in Renly. amount/amount_currency/
    # base_amount store both sides of a cross-currency move and never a derived rate, exactly as
    # transfers and card_settlements already do. unit_price is kept for audit: it is derivable from
    # NAV at the date, but NAV moves as later snapshots arrive, so the price actually used has to be
    # recorded at the moment it is used.
    # from_account_id / to_account_id are what make the event a real MOVEMENT rather than a note about
    # one — a contribution debits the mover's private account and credits an account the pot holds,
    # and the per-account balance union reads both legs. Two columns for the same reason transfers has
    # two: this IS the transfer mechanic at a different scope.
    op.create_table(
        "pot_ownership_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("pot_id", sa.BigInteger(), sa.ForeignKey("pots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", postgresql.ENUM(name="ownership_event_type", create_type=False), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_member_id", sa.BigInteger(), sa.ForeignKey("group_members.id", ondelete="CASCADE"), nullable=True),
        sa.Column("amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("amount_currency", sa.String(length=3), nullable=True),
        sa.Column("base_amount", sa.Numeric(18, 2), nullable=True),
        sa.Column("units", sa.Numeric(18, 6), nullable=False),
        sa.Column("unit_price", sa.Numeric(18, 6), nullable=False),
        sa.Column("from_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("to_account_id", sa.BigInteger(), sa.ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.CheckConstraint(
            "(type = 'reagreement') = (counterparty_member_id IS NOT NULL) "
            "AND (counterparty_member_id IS NULL OR counterparty_member_id <> member_id)",
            name="pot_ownership_events_counterparty",
        ),
        sa.CheckConstraint("unit_price > 0", name="pot_ownership_events_positive_price"),
        # Only a contribution or a withdrawal moves money: an opening sets a division baseline and a
        # reagreement moves units between people, so naming an account on either would record a
        # movement that did not happen.
        sa.CheckConstraint(
            "type IN ('contribution', 'withdrawal') "
            "OR (from_account_id IS NULL AND to_account_id IS NULL AND amount IS NULL AND amount_currency IS NULL)",
            name="pot_ownership_events_movement",
        ),
        # Same reason transfers forbids it: the balance union sums each leg independently, so one
        # account on both sides would be added and subtracted at once — a silent no-op.
        sa.CheckConstraint(
            "from_account_id IS NULL OR to_account_id IS NULL OR from_account_id <> to_account_id",
            name="pot_ownership_events_distinct_accounts",
        ),
    )
    op.create_index("idx_pot_ownership_events_pot_date", "pot_ownership_events", ["pot_id", "date"])
    op.create_index("idx_pot_ownership_events_member_id", "pot_ownership_events", ["member_id"])
    op.create_index(
        "idx_pot_ownership_events_counterparty_member_id",
        "pot_ownership_events",
        ["counterparty_member_id"],
        postgresql_where=sa.text("counterparty_member_id IS NOT NULL"),
    )
    # The balance union filters one leg at a time by account and bounds by date, so each leg gets its
    # own composite index rather than a bare FK index — the same shape transfers uses.
    op.create_index(
        "idx_pot_ownership_events_from_account_date",
        "pot_ownership_events",
        ["from_account_id", "date"],
        postgresql_where=sa.text("from_account_id IS NOT NULL"),
    )
    op.create_index(
        "idx_pot_ownership_events_to_account_date",
        "pot_ownership_events",
        ["to_account_id", "date"],
        postgresql_where=sa.text("to_account_id IS NOT NULL"),
    )

    for table in ("pots", "pot_member_permissions", "pot_ownership_events"):
        op.execute(f"CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION set_updated_at()")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO renly_app")
    # pot_member_permissions has a composite primary key and therefore no sequence of its own.
    for table in ("pots", "pot_ownership_events"):
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO renly_app")

    # The destructive half. ON DELETE RESTRICT on every pot_id FK is the whole safety story: CASCADE
    # would let deleting a pot (or the group above it) destroy real holdings, and SET NULL would
    # violate the single-owner CHECK by leaving a row with neither owner. A pot that still holds
    # anything therefore cannot be deleted at all.
    for table in _SCOPED_TABLES:
        op.add_column(table, sa.Column("pot_id", sa.BigInteger(), nullable=True))
        op.create_foreign_key(f"{table}_pot_id_fkey", table, "pots", ["pot_id"], ["id"], ondelete="RESTRICT")
        op.create_index(_POT_INDEX[table], table, ["pot_id"], postgresql_where=sa.text("pot_id IS NOT NULL"))
        op.alter_column(table, "user_id", existing_type=sa.BigInteger(), nullable=True)
        op.create_check_constraint(f"{table}_single_owner", table, "(user_id IS NOT NULL) <> (pot_id IS NOT NULL)")

    # created_by is nullable + SET NULL for the same reason groups.created_by is: a shared holding
    # outlives the account that entered it, and NOT NULL leaves no ON DELETE that works — SET NULL
    # would violate it and RESTRICT would block account deletion on a row the user cannot reach.
    # Backfilled from user_id, which at this revision is still the author for every existing row:
    # nothing could have created a shared holding before this migration ran.
    for table in _AUTHORED_TABLES:
        op.add_column(table, sa.Column("created_by", sa.BigInteger(), nullable=True))
        op.create_foreign_key(f"{table}_created_by_fkey", table, "users", ["created_by"], ["id"], ondelete="SET NULL")
        op.create_index(f"idx_{table}_created_by", table, ["created_by"])
        op.execute(f"UPDATE {table} SET created_by = user_id")

    # Same SECURITY DEFINER shape and the same reasons as app_is_group_member: the body runs as the
    # owner (exempt from RLS) so a policy on a scoped table can consult pot_member_permissions
    # without recursing, search_path is pinned, and the default PUBLIC EXECUTE grant every function
    # receives is revoked because this one runs as the table owner.
    # The COALESCE in the view helper is load-bearing: a member who joins the group AFTER a pot was
    # created has no permission row at all, and reading the pot's own visibility default there is
    # what lets them see a 'members' pot with no seeding step anywhere. `role` appears in neither
    # helper — administration never grants visibility, enforced by the shape rather than by anyone
    # remembering the rule.
    op.execute(_APP_CAN_VIEW_POT_SQL)
    op.execute(_APP_CAN_WRITE_POT_SQL)
    for fn in ("app_can_view_pot", "app_can_write_pot"):
        op.execute(f"REVOKE ALL ON FUNCTION {fn}(BIGINT) FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION {fn}(BIGINT) TO renly_app")

    # Swap each owner-match policy for the dual-scope pair. A query that forgets the pot branch now
    # returns FEWER rows; it cannot surface anyone else's money.
    for table in _SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {_LEGACY_POLICY[table]} ON {table}")
        for statement in _scope_policies(table):
            op.execute(statement)

    # The pot tables. Membership alone is NOT the read predicate: a pot set to 'owners' visibility
    # must be invisible to a member without permission, including the fact that it exists. The write
    # policy's USING carries app_can_view_pot too, because permissive policies are OR-ed and a bare
    # membership USING would have quietly widened SELECT back to every member.
    # WITH CHECK on pots stays membership-only: a pot's first permission row does not exist while the
    # pot is being created, so requiring view on the new row would refuse the very insert that
    # establishes it — the same self-referential bootstrap group creation has, with the same answer
    # (pot creation runs on the privileged session).
    op.execute("ALTER TABLE pots ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY pots_scope_read ON pots FOR SELECT USING (app_can_view_pot(id))")
    op.execute(
        "CREATE POLICY pots_scope_write ON pots FOR ALL "
        "USING (app_can_view_pot(id) AND app_is_group_member(group_id)) "
        "WITH CHECK (app_is_group_member(group_id))"
    )

    # WITH CHECK here is the load-bearing half: without it any authenticated user could insert a
    # permission row naming any pot id and their own seat, and read themselves straight into someone
    # else's shared money. Requiring view on the new row means a permission row can only be written
    # for a pot the writer can already see, so no row here widens the set of pots anyone can reach.
    op.execute("ALTER TABLE pot_member_permissions ENABLE ROW LEVEL SECURITY")
    op.execute("CREATE POLICY pot_member_permissions_scope_read ON pot_member_permissions FOR SELECT USING (app_can_view_pot(pot_id))")
    op.execute(
        "CREATE POLICY pot_member_permissions_scope_write ON pot_member_permissions FOR ALL "
        "USING (app_can_view_pot(pot_id)) WITH CHECK (app_can_view_pot(pot_id))"
    )

    # Genuine money movement rather than configuration, so app_can_write_pot is the right gate and
    # the service is not the only thing standing between a read-only custodian and the ledger.
    op.execute("ALTER TABLE pot_ownership_events ENABLE ROW LEVEL SECURITY")
    # The second read branch keeps a PRIVATE balance correct rather than widening the visibility
    # model. A contribution debits the mover's own account, so the event is a movement in that
    # account's ledger; if they later leave the group the pot branch stops matching and their private
    # account silently gains back money it no longer holds. It matches only rows naming an account the
    # caller OWNS, and the service requires the moving member to own the private leg, so every row it
    # returns is the caller's own movement.
    op.execute(
        "CREATE POLICY pot_ownership_events_scope_read ON pot_ownership_events FOR SELECT USING ("
        "app_can_view_pot(pot_id) OR EXISTS ("
        "SELECT 1 FROM accounts a "
        "WHERE a.id IN (pot_ownership_events.from_account_id, pot_ownership_events.to_account_id) "
        "AND a.user_id = app_current_user_id()))"
    )
    op.execute(
        "CREATE POLICY pot_ownership_events_scope_write ON pot_ownership_events FOR ALL "
        "USING (app_can_write_pot(pot_id)) WITH CHECK (app_can_write_pot(pot_id))"
    )


# Reverses everything upgrade() created, and REFUSES rather than guesses when it cannot.
#
# The refusal is the honest part. Once a holding belongs to a pot there is no column below this
# revision to put it in: restoring user_id NOT NULL would either fail on a NULL or, if this function
# "helpfully" picked an owner, silently hand one member the whole of something several people own.
# Deleting the rows instead would destroy real money records to satisfy a schema change. So a
# downgrade with any shared row raises and names the tables, and the operator un-shares first — the
# same posture as reconciliation refusing to invent a figure.
#
# With no shared rows the downgrade is exact: user_id is NOT NULL on every row already, so the
# constraint goes back on unchanged and the schema returns to its pre-0019 state.
def downgrade() -> None:
    bind = op.get_bind()
    shared = [t for t in _SCOPED_TABLES if bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {t} WHERE pot_id IS NOT NULL)")).scalar()]
    if shared:
        raise RuntimeError(
            "Cannot downgrade past 0019: co-owned rows exist in " + ", ".join(shared) + ". "
            "There is no owner column below this revision to hold them, and neither deleting them nor "
            "assigning them to one member would be true. Move them back to a private owner first."
        )

    op.execute("DROP POLICY IF EXISTS pot_ownership_events_scope_write ON pot_ownership_events")
    op.execute("DROP POLICY IF EXISTS pot_ownership_events_scope_read ON pot_ownership_events")
    op.execute("DROP POLICY IF EXISTS pot_member_permissions_scope_write ON pot_member_permissions")
    op.execute("DROP POLICY IF EXISTS pot_member_permissions_scope_read ON pot_member_permissions")
    op.execute("DROP POLICY IF EXISTS pots_scope_write ON pots")
    op.execute("DROP POLICY IF EXISTS pots_scope_read ON pots")

    # Restore the owner-match policy each table had, worded exactly as 0003/0010/0012/0014 wrote it.
    for table in _SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_write ON {table}")
        op.execute(f"DROP POLICY IF EXISTS {table}_scope_read ON {table}")
        op.execute(
            f"CREATE POLICY {_LEGACY_POLICY[table]} ON {table} "
            "USING (user_id = app_current_user_id()) WITH CHECK (user_id = app_current_user_id())"
        )

    # Dropped only after every policy that calls them is gone, or the DROP is refused as a dependency.
    op.execute("DROP FUNCTION IF EXISTS app_can_write_pot(BIGINT)")
    op.execute("DROP FUNCTION IF EXISTS app_can_view_pot(BIGINT)")

    for table in reversed(_AUTHORED_TABLES):
        op.drop_index(f"idx_{table}_created_by", table_name=table)
        op.drop_constraint(f"{table}_created_by_fkey", table, type_="foreignkey")
        op.drop_column(table, "created_by")

    for table in reversed(_SCOPED_TABLES):
        op.drop_constraint(f"{table}_single_owner", table, type_="check")
        op.alter_column(table, "user_id", existing_type=sa.BigInteger(), nullable=False)
        op.drop_index(_POT_INDEX[table], table_name=table)
        op.drop_constraint(f"{table}_pot_id_fkey", table, type_="foreignkey")
        op.drop_column(table, "pot_id")

    for table in ("pot_ownership_events", "pot_member_permissions", "pots"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table}")

    op.drop_index("idx_pot_ownership_events_to_account_date", table_name="pot_ownership_events")
    op.drop_index("idx_pot_ownership_events_from_account_date", table_name="pot_ownership_events")
    op.drop_index("idx_pot_ownership_events_counterparty_member_id", table_name="pot_ownership_events")
    op.drop_index("idx_pot_ownership_events_member_id", table_name="pot_ownership_events")
    op.drop_index("idx_pot_ownership_events_pot_date", table_name="pot_ownership_events")
    op.drop_table("pot_ownership_events")
    op.drop_index("idx_pot_member_permissions_member_id", table_name="pot_member_permissions")
    op.drop_table("pot_member_permissions")
    op.drop_index("idx_pots_group_default", table_name="pots")
    op.drop_index("idx_pots_group_id", table_name="pots")
    op.drop_table("pots")

    postgresql.ENUM(name="ownership_event_type").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="pot_visibility").drop(op.get_bind(), checkfirst=True)
