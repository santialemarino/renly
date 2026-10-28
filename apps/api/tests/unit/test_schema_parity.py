# The canonical schema file and the migrations have to describe the same database, and for SQL
# FUNCTIONS that means byte-identical bodies, not merely equivalent ones.
#
# pg_dump reproduces a function body verbatim, so the same helper indented differently in
# database/01_create_tables.sql and in its migration makes a freshly-initialised database and a
# migrated one differ TEXTUALLY while behaving identically — which is exactly the difference a
# fresh-vs-migrated pg_dump comparison exists to catch, and exactly the noise that makes such a
# comparison stop being trustworthy.
#
# The 0018 build record says this guard was added when the problem was first found. It was not: the
# migration carries a comment promising byte-identity and nothing checked it. This is that check.

import pathlib
import re

API_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = API_ROOT / "database" / "01_create_tables.sql"
MIGRATIONS = API_ROOT / "migrations" / "versions"

# Every function the schema defines, by name. Derived from the file rather than listed here, so a
# helper added without a migration copy is caught instead of silently skipped.
# `AS $$` anchors the body start and the next `$$` closes it, which handles both shapes in the file:
# a one-line body and an indented multi-line one.
_FUNCTION = re.compile(r"CREATE OR REPLACE FUNCTION (\w+)\(.*?AS (\$\$.*?\$\$)", re.S)


# Returns {name: body} for every function in the canonical schema, where "body" is only the text
# BETWEEN the dollar quotes. That is deliberately narrower than the whole statement: Postgres stores
# and pg_dump reproduces the body verbatim, while the header (RETURNS / LANGUAGE / SET search_path) is
# regenerated from catalog metadata — so a migration is free to wrap its header differently, and
# several already do, without producing any difference in the resulting database.
def _schema_functions() -> dict[str, str]:
    text = SCHEMA.read_text()
    return {match.group(1): match.group(2) for match in _FUNCTION.finditer(text)}


def _migration_text() -> str:
    return "\n".join(path.read_text() for path in sorted(MIGRATIONS.glob("*.py")))


# `CREATE TABLE <name> (` … the `);` that closes it at the start of a line.
_TABLE = re.compile(r"^CREATE TABLE (\w+) \((.*?)^\);", re.M | re.S)


# {table: its column names} for every table the canonical schema creates, columns read from the CREATE
# body (a line starting with an identifier; CONSTRAINT / UNIQUE / PRIMARY KEY lines are not columns) plus
# any `ALTER TABLE … ADD COLUMN` later in the file.
def _schema_tables() -> dict[str, set[str]]:
    text = SCHEMA.read_text()
    keywords = {"CONSTRAINT", "UNIQUE", "PRIMARY", "FOREIGN", "CHECK", "EXCLUDE"}
    tables = {
        name: {column for column in re.findall(r"^\s+(\w+)\s", body, re.M) if column.upper() not in keywords} for name, body in _TABLE.findall(text)
    }
    for table, column in re.findall(r"ALTER TABLE (\w+)\s+ADD COLUMN (?:IF NOT EXISTS )?(\w+)", text):
        tables[table].add(column)
    return tables


# The dual-scope tables: those a row of which belongs EITHER to a user or to a pot. Derived from the
# columns, so a seventh such table is held to the guards below by existing, instead of passing because
# nobody added it to a list.
def _dual_scope_tables() -> tuple[str, ...]:
    return tuple(sorted(name for name, columns in _schema_tables().items() if {"user_id", "pot_id"} <= columns))


class TestFunctionBodiesMatchTheirMigration:
    def test_every_function_a_migration_defines_matches_the_schema_file_verbatim(self):
        # Scoped to functions some migration actually DEFINES. set_updated_at() is deliberately not
        # one: it ships only in the canonical schema and every migration that needs it says so, since
        # migrations never run against an empty database (db:init applies the SQL file and stamps to
        # head). Requiring a copy of it here would invent a rule the repo never made.
        #
        # "Some" migration rather than a named one, because when a later revision redefines a helper
        # the schema file carries the NEW body and that revision is the one holding it — the older
        # copy is correctly left describing the schema at its own revision.
        migrations = _migration_text()
        # `CREATE OR REPLACE FUNCTION <name>(`, not just the name: every trigger creation says
        # `EXECUTE FUNCTION set_updated_at()`, which is a CALL and not a definition.
        defined = {name: body for name, body in _schema_functions().items() if f"CREATE OR REPLACE FUNCTION {name}(" in migrations}
        missing = [name for name, body in defined.items() if body not in migrations]
        assert missing == [], f"function bodies differ between the schema file and every migration: {missing}"

    def test_the_helpers_this_guard_exists_for_are_actually_being_checked(self):
        # Without this, a regex that quietly stopped matching would make the test above vacuously
        # pass — the failure mode where a guard is green because it is checking nothing.
        names = set(_schema_functions())
        assert {
            "app_current_user_id",
            "app_is_group_member",
            "app_can_view_pot",
            "app_can_write_pot",
            "app_reconciliation_follows_account",
            "app_transfer_follows_accounts",
        } <= names


class TestScopedTablesCarryTheirGuards:
    # The dual-scope tables all need the same three objects, and a table that gained a pot_id without
    # one of them would fail open (no CHECK) or fail closed in the wrong place (no policy). DERIVED from
    # the schema: this was a hand-written 6-tuple, so a seventh dual-scope table with no single-owner
    # CHECK and no RLS at all passed every assertion in this class.
    SCOPED = _dual_scope_tables()

    def test_the_derived_population_is_the_one_the_schema_holds(self):
        # Anti-vacuity: a column regex that stopped matching would derive an empty tuple, and every
        # assertion in this class would pass over it. The six named here are the tables that existed when
        # the derivation replaced the list; more may join, none may vanish without this failing.
        assert {"investments", "investment_snapshots", "transactions", "accounts", "account_reconciliations", "transfers"} <= set(self.SCOPED)

    def test_every_scoped_table_is_policied_and_forced(self):
        text = SCHEMA.read_text()
        missing = [
            t
            for t in self.SCOPED
            if f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY;" not in text or f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY;" not in text
        ]
        assert missing == [], f"dual-scope tables without RLS enabled and forced: {missing}"

    def test_every_scoped_table_has_a_single_owner_check(self):
        text = SCHEMA.read_text()
        missing = [t for t in self.SCOPED if f"CONSTRAINT {t}_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))" not in text]
        assert missing == [], f"tables with pot_id but no single-owner CHECK: {missing}"

    # The one scoped table whose write half is NOT pot write access, and so does not carry a
    # `_scope_write FOR ALL` policy at all. Reconciling a pot's account is gated on SEEING the pot —
    # the same gate the equivalent manual act carries — so it splits per command instead: insert,
    # update and delete each on the view predicate, with a column grant capping what an update may set.
    # Listed here rather than dropped from SCOPED, because every OTHER assertion in this class still
    # applies to it.
    VIEW_GATED_WRITES = ("account_reconciliations",)

    def test_every_scoped_table_has_BOTH_a_read_and_a_write_policy(self):
        # Two policies, not one: Postgres has no WITH CHECK for DELETE, so a single FOR ALL policy
        # whose USING named the view helper would let a read-only member delete a shared holding.
        text = SCHEMA.read_text()
        missing = [
            t
            for t in self.SCOPED
            if t not in self.VIEW_GATED_WRITES
            and (f"CREATE POLICY {t}_scope_read ON {t} FOR SELECT" not in text or f"CREATE POLICY {t}_scope_write ON {t} FOR ALL" not in text)
        ]
        assert missing == [], f"tables missing a read or write policy: {missing}"

    def test_the_view_gated_table_splits_its_writes_per_command(self):
        # The exemption is not a hole. Postgres has no WITH CHECK for DELETE, so the same reasoning
        # that gives every other table two policies gives this one four — and the read-only seat it
        # deliberately admits makes each verb's predicate load-bearing on its own.
        text = SCHEMA.read_text()
        for table in self.VIEW_GATED_WRITES:
            assert f"CREATE POLICY {table}_scope_write ON {table} FOR ALL" not in text, table
            for command in ("SELECT", "INSERT", "UPDATE", "DELETE"):
                policy = f"{table}_scope_{'read' if command == 'SELECT' else command.lower()}"
                assert f"CREATE POLICY {policy} ON {table} FOR {command}" in text, f"{table}: {command}"
            # RLS filters rows and never columns, so only a REVOKE plus a per-column GRANT can stop the
            # read-only seat this table admits from rewriting a figure somebody else recorded. The GRANT
            # is matched across the line break it is written on and tied to THIS table, so it cannot be
            # satisfied by a per-column grant somewhere else in the schema.
            assert f"REVOKE UPDATE ON {table} FROM renly_app" in text, table
            grant = re.search(rf"GRANT UPDATE \(([^)]*)\)\s*\n?\s*ON {table} TO renly_app", text)
            assert grant is not None, f"{table}: no per-column UPDATE grant"
            # Exactly the four back-pointer columns and the scope pair a move between scopes re-points,
            # and never an amount or a date. `updated_at` is deliberately absent: column privileges are
            # checked against a statement's SET list and the trigger writes that one.
            assert [c.strip() for c in grant.group(1).split(",")] == [
                "adjustment_expense_id",
                "adjustment_income_id",
                "adjustment_shared_expense_id",
                "adjustment_shared_income_id",
                "user_id",
                "pot_id",
            ], table

    def test_no_scoped_table_kept_its_old_owner_only_policy(self):
        # A leftover permissive owner-match policy would be OR-ed with the new pair and silently
        # restore the pre-0019 behaviour for reads.
        text = SCHEMA.read_text()
        leftovers = [t for t in self.SCOPED if f"CREATE POLICY {t}_user_isolation" in text]
        assert leftovers == [], f"tables still carrying the pre-0019 owner-only policy: {leftovers}"

    def test_role_appears_in_no_pot_visibility_predicate(self):
        # "Administration never grants visibility" is enforced by the SHAPE of the helpers, so the
        # word must not appear in either of them. Asserted on the text because that is the level at
        # which the guarantee is made.
        for name in ("app_can_view_pot", "app_can_write_pot"):
            body = _schema_functions()[name]
            assert "role" not in body, f"{name} consults a role"


# The tables that hold NO tenant's rows and so carry no RLS: global reference data every user reads alike,
# written only by the scheduler. Pinned by name AND reason, and compared both ways below — a table may
# join this list only by writing down why it is nobody's. `tests/integration/test_rls_force_role_model.py`
# holds the live catalogue to the same list.
GLOBAL_REFERENCE_TABLES = {
    "asset_prices": "Daily market prices per ticker, fetched by the scheduler; identical for every user.",
    "cedear_ratios": "CEDEAR-to-underlying conversion ratios, fetched by the scheduler; identical for every user.",
    "exchange_rates": "Daily currency-pair rates, fetched by the scheduler; identical for every user.",
}


class TestRowLevelSecurityCoversEveryTenantTable:
    # The static twin of the catalogue checks in `tests/integration/test_rls_force_role_model.py`, read off
    # the canonical schema so a table created without its ENABLE / FORCE fails on every commit, without a
    # database. The live check stays the authority (a migration can diverge from this file).

    @staticmethod
    def _rls() -> tuple[set[str], set[str], set[str]]:
        text = SCHEMA.read_text()
        enabled = set(re.findall(r"ALTER TABLE (\w+) ENABLE ROW LEVEL SECURITY", text))
        forced = set(re.findall(r"ALTER TABLE (\w+) FORCE ROW LEVEL SECURITY", text))
        policied = set(re.findall(r"CREATE POLICY \w+\s+ON (\w+)", text))
        return enabled, forced, policied

    def test_every_policied_table_is_enabled_and_forced(self):
        # A policy on a table with RLS off is decoration: every role reads every row.
        enabled, forced, policied = self._rls()
        assert sorted(policied - (enabled & forced)) == []

    def test_every_rls_table_has_a_policy(self):
        # The other direction: RLS on with no policy denies every row to the request role, silently.
        enabled, forced, policied = self._rls()
        assert sorted((enabled | forced) - policied) == []

    def test_the_only_tables_without_rls_are_the_global_reference_tables(self):
        enabled, forced, _ = self._rls()
        without = set(_schema_tables()) - (enabled & forced)
        assert without == set(GLOBAL_REFERENCE_TABLES), f"tables without RLS enabled and forced, against the named exceptions: {sorted(without)}"

    def test_the_exception_list_is_pinned(self):
        # Pinned to a number on purpose: growing it is a decision about who may read a table, and a test
        # that moves with the list cannot notice the list moving.
        assert len(GLOBAL_REFERENCE_TABLES) == 3
        assert all(reason.strip() for reason in GLOBAL_REFERENCE_TABLES.values())
        tables = _schema_tables()
        scoped = [t for t in GLOBAL_REFERENCE_TABLES if tables[t] & {"user_id", "group_id", "pot_id"}]
        assert scoped == [], f"a 'global' table carries a tenant column: {scoped}"

    def test_the_parse_finds_the_schema(self):
        # Anti-vacuity: every assertion above is satisfied by a regex that matched nothing.
        enabled, forced, policied = self._rls()
        assert len(_schema_tables()) >= 42
        assert len(enabled & forced) >= 39 and len(policied) >= 39
