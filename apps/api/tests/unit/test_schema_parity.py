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
        assert {"app_current_user_id", "app_is_group_member", "app_can_view_pot", "app_can_write_pot"} <= names


class TestScopedTablesCarryTheirGuards:
    # The dual-scope tables all need the same three objects, and a table that gained a pot_id without
    # one of them would fail open (no CHECK) or fail closed in the wrong place (no policy).
    SCOPED = (
        "investments",
        "investment_snapshots",
        "transactions",
        "accounts",
        "account_reconciliations",
        "transfers",
    )

    def test_every_scoped_table_has_a_single_owner_check(self):
        text = SCHEMA.read_text()
        missing = [t for t in self.SCOPED if f"CONSTRAINT {t}_single_owner CHECK ((user_id IS NOT NULL) <> (pot_id IS NOT NULL))" not in text]
        assert missing == [], f"tables with pot_id but no single-owner CHECK: {missing}"

    def test_every_scoped_table_has_BOTH_a_read_and_a_write_policy(self):
        # Two policies, not one: Postgres has no WITH CHECK for DELETE, so a single FOR ALL policy
        # whose USING named the view helper would let a read-only member delete a shared holding.
        text = SCHEMA.read_text()
        missing = [
            t
            for t in self.SCOPED
            if f"CREATE POLICY {t}_scope_read ON {t} FOR SELECT" not in text or f"CREATE POLICY {t}_scope_write ON {t} FOR ALL" not in text
        ]
        assert missing == [], f"tables missing a read or write policy: {missing}"

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
