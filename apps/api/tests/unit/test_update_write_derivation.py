import textwrap

from tests.integration.test_update_column_privileges import APP, Write, _refusals, derive_writes

# The derivation behind tests/integration/test_update_column_privileges.py, pinned without a database.
#
# That test compares every UPDATE the application can issue with what the request role may update, and
# it is only as good as the list of writes it is handed: a walk that stopped recognising a shape would
# leave the comparison green over exactly the writes it can no longer see. This half runs on every
# `pnpm test:api`, so a broken walk fails here even where no database is configured. Each shape is
# exercised on a small synthetic module, and the known real sites are asserted by name, so the walk
# breaking reads differently from the codebase legitimately changing.

_PROBE = APP / "services" / "update_probe.py"

_HEADER = """
from sqlalchemy import select, text, update
from sqlalchemy import update as sa_update
from sqlalchemy.dialects.postgresql import insert
from app.models import AccountReconciliation, Account
"""


# The writes derived from one synthetic module, as (kind, tables, columns) with the site dropped.
def _derive(body: str) -> set[tuple[str, frozenset[str], frozenset[str] | None]]:
    source = _HEADER + textwrap.dedent(body)
    return {(w.kind, w.tables, w.columns) for w in derive_writes({_PROBE: source})}


_RECON = frozenset({"account_reconciliations"})


class TestEachUpdateShapeIsDerived:
    def test_core_update_keywords(self):
        found = _derive("""
            async def f(session, ids):
                await session.execute(update(AccountReconciliation).where(AccountReconciliation.id.in_(ids)).values(statement_balance=1))
        """)
        assert found == {("core update", _RECON, frozenset({"statement_balance"}))}

    def test_core_update_through_an_alias_and_a_dict_spread(self):
        # The exact shape move_to_scope uses, which is the one that shipped refused.
        found = _derive("""
            async def f(session, ids, pot_id, user_id):
                values = {"pot_id": pot_id, "user_id": user_id}
                await session.execute(sa_update(AccountReconciliation).where(AccountReconciliation.account_id.in_(ids)).values(**values))
        """)
        assert found == {("core update", _RECON, frozenset({"pot_id", "user_id"}))}

    def test_core_update_built_up_through_a_local_name(self):
        found = _derive("""
            async def f(session):
                stmt = update(AccountReconciliation)
                stmt = stmt.values({AccountReconciliation.difference: 0})
                await session.execute(stmt)
        """)
        assert found == {("core update", _RECON, frozenset({"difference"}))}

    def test_a_spread_of_something_other_than_a_literal_is_unknown_not_empty(self):
        # Fails loudly: None is "cannot tell", which the comparison refuses on a per-column table. An
        # empty set here would be "sets nothing", which it would pass.
        found = _derive("""
            async def f(session, build):
                values = build()
                await session.execute(update(AccountReconciliation).values(**values))
        """)
        assert found == {("core update", _RECON, None)}

    def test_an_update_with_no_values_in_sight_is_unknown(self):
        # e.g. an executemany-style `session.execute(update(M), [{...}])`, whose SET list is the rows'.
        found = _derive("""
            async def f(session, rows):
                await session.execute(update(AccountReconciliation), rows)
        """)
        assert found == {("core update", _RECON, None)}

    def test_an_insert_is_not_an_update(self):
        found = _derive("""
            async def f(session):
                await session.execute(insert(AccountReconciliation).values(statement_balance=1))
        """)
        assert found == set()

    def test_an_upsert_sets_the_keys_of_its_set_clause(self):
        found = _derive("""
            async def f(session):
                stmt = insert(AccountReconciliation).values(statement_balance=1)
                stmt = stmt.on_conflict_do_update(index_elements=["id"], set_={"difference": stmt.excluded.difference})
                await session.execute(stmt)
        """)
        assert found == {("upsert", _RECON, frozenset({"difference"}))}

    def test_an_orm_write_on_an_annotated_parameter(self):
        found = _derive("""
            async def f(session, reconciliation: AccountReconciliation):
                reconciliation.statement_balance = 1
        """)
        assert found == {("orm attribute", _RECON, frozenset({"statement_balance"}))}

    def test_an_orm_write_on_a_row_a_repository_returned(self):
        # Typed through the callee's return annotation, which is how almost every real write is typed.
        found = _derive("""
            async def load(session) -> AccountReconciliation | None:
                return None

            async def f(session):
                reconciliation = await load(session)
                reconciliation.difference = 0
        """)
        assert found == {("orm attribute", _RECON, frozenset({"difference"}))}

    def test_an_orm_write_on_one_element_of_an_unpacked_tuple(self):
        found = _derive("""
            async def load(session) -> tuple[Account, AccountReconciliation]:
                return None

            async def f(session):
                account, reconciliation = await load(session)
                reconciliation.difference = 0
                account.name = "x"
        """)
        assert found == {
            ("orm attribute", _RECON, frozenset({"difference"})),
            ("orm attribute", frozenset({"accounts"}), frozenset({"name"})),
        }

    def test_an_orm_write_on_a_selected_row(self):
        found = _derive("""
            async def f(session):
                result = await session.execute(select(AccountReconciliation).where(AccountReconciliation.id == 1))
                for row in result.scalars().all():
                    row.difference = 0
        """)
        assert found == {("orm attribute", _RECON, frozenset({"difference"}))}

    def test_an_orm_write_on_an_object_of_unknown_type_counts_against_every_table_with_that_column(self):
        # The conservative direction: an untyped `x.difference = …` could be either table carrying it.
        found = _derive("""
            async def f(session, thing):
                thing.statement_balance = 1
        """)
        both = frozenset({"account_reconciliations", "card_reconciliations"})
        assert found == {("orm attribute (untyped)", both, frozenset({"statement_balance"}))}

    def test_a_setattr_with_a_computed_name_is_unknown(self):
        found = _derive("""
            async def f(session, reconciliation: AccountReconciliation, fields):
                for key, value in fields.items():
                    setattr(reconciliation, key, value)
                setattr(reconciliation, "difference", 0)
        """)
        assert found == {("orm setattr", _RECON, None), ("orm setattr", _RECON, frozenset({"difference"}))}

    def test_a_merge_can_set_anything(self):
        found = _derive("""
            async def f(session, reconciliation: AccountReconciliation):
                await session.merge(reconciliation)
        """)
        assert found == {("orm merge", _RECON, None)}

    def test_raw_sql_names_its_table_and_its_set_list(self):
        found = _derive("""
            async def f(session):
                await session.execute(text("UPDATE account_reconciliations SET statement_balance = 1, difference = 2 WHERE id = 1"))
        """)
        assert found == {("raw sql", _RECON, frozenset({"statement_balance", "difference"}))}


class TestTheComparison:
    # Grants shaped like the real schema's: one table fully granted, one granted per column.
    _WHOLE = {"accounts": True, "account_reconciliations": False}
    _PER_COLUMN = {"account_reconciliations": {"user_id", "pot_id"}}

    def test_a_column_outside_a_per_column_grant_is_refused(self):
        writes = [Write("a:1", "core update", _RECON, frozenset({"pot_id", "difference"}))]
        assert _refusals(writes, self._WHOLE, self._PER_COLUMN) == [
            "a:1 (core update): account_reconciliations.difference is not updatable by renly_app"
        ]

    def test_unknown_columns_are_refused_only_where_the_grant_is_per_column(self):
        writes = [Write("a:1", "orm merge", _RECON, None), Write("a:2", "orm setattr", frozenset({"accounts"}), None)]
        assert _refusals(writes, self._WHOLE, self._PER_COLUMN) == [
            "a:1 (orm merge): cannot derive which columns it sets, and account_reconciliations grants UPDATE per column"
        ]

    def test_a_table_with_no_update_at_all_refuses_every_write(self):
        writes = [Write("a:1", "core update", frozenset({"shared_audit_log"}), frozenset({"payload"}))]
        assert _refusals(writes, {"shared_audit_log": False}, {}) == ["a:1 (core update): shared_audit_log.payload is not updatable by renly_app"]


class TestTheRealSitesAreFound:
    # Named sites, one per shape the codebase actually uses on a per-column table today, so the walk
    # breaking fails here rather than letting the comparison run over a shorter list.
    # The real application's writes, as (file, tables, columns).
    def _found(self) -> set[tuple[str, frozenset[str], frozenset[str] | None]]:
        return {(w.site.split(":")[0], w.tables, w.columns) for w in derive_writes()}

    def test_the_scope_move_re_points_the_reconciliations(self):
        assert ("app/repositories/account_repository.py", _RECON, frozenset({"pot_id", "user_id"})) in self._found()

    def test_the_adjustment_back_pointers_are_orm_writes_on_the_reconciliation(self):
        found = self._found()
        for column in ("adjustment_expense_id", "adjustment_income_id", "adjustment_shared_expense_id", "adjustment_shared_income_id"):
            assert ("app/services/account_reconciliation_service.py", _RECON, frozenset({column})) in found, column

    def test_a_re_agreement_confirmation_is_typed_to_its_event_not_to_the_settlement_beside_it(self):
        # Both tables carry confirmed_at; only the typing tells them apart, and only one is per-column.
        found = self._found()
        assert ("app/services/pot_ownership_service.py", frozenset({"pot_ownership_events"}), frozenset({"confirmed_at"})) in found
        assert ("app/services/group_settlement_service.py", frozenset({"group_settlements"}), frozenset({"confirmed_at"})) in found
