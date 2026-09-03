# The /income union (PR 6) and X2's grouping on top of it: the user's own entries and their SHARE of
# every piece of income their group seats are entitled to, as one list.
#
# The mirror of test_expenses_union, deliberately assertion-for-assertion parallel — PR 8a's sharpest
# finding was two helpers their own comments called mirrors having quietly stopped projecting the same
# columns, and the gap only became writable as a mutation once they matched again. The rows the query
# actually returns are proved against a real database in tests/integration; these pin the two things
# reachable without one — the statement's shape, and how a row becomes a response.

from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.list_scope import ListScope
from app.models.income_entry import IncomeCategory
from app.models.user import User
from app.repositories import income_repository
from app.repositories.income_repository import SCOPE_PRIVATE, SCOPE_SHARED, SOURCE_SHARED, IncomeListRow
from app.services import income_service

USER = User(id=1, name="S", email="u@test", password_hash="x", session_epoch=0)


# The compiled SQL of the list statement, which is the only part of the query reachable without a DB.
class _CapturingSession:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement):
        self.statements.append(str(statement.compile(compile_kwargs={"literal_binds": True})))
        return _Result()


class _Result:
    def scalar_one(self):
        return 0

    def all(self):
        return []


async def _compile(member_ids: list[int], **kwargs) -> list[str]:
    session = _CapturingSession()
    await income_repository.list_by_user_filtered(session, USER.id, member_ids, **kwargs)
    return session.statements


async def _compile_sums(member_ids: list[int], **kwargs) -> str:
    session = _CapturingSession()
    await income_repository.sum_by_scope(session, USER.id, member_ids, **kwargs)
    return session.statements[0]


class TestTheStatementShape:
    @pytest.mark.asyncio
    async def test_a_user_in_no_group_gets_no_union_at_all(self):
        # Every user at launch is in no group. Building a union whose second branch can only ever be
        # empty would make all of them pay for a feature they do not have.
        for sql in await _compile([]):
            assert "shared_income_splits" not in sql
            assert "UNION" not in sql

    @pytest.mark.asyncio
    async def test_a_member_gets_both_branches(self):
        for sql in await _compile([7]):
            assert "UNION ALL" in sql
            assert "income_entries" in sql and "shared_income_splits" in sql

    @pytest.mark.asyncio
    async def test_the_shared_branch_is_keyed_on_the_callers_own_seats(self):
        # An IN over the seats, not a join to group_members: the join makes Postgres scan every split
        # in the database, and the seats are resolved by the service anyway.
        sql = (await _compile([7, 9]))[0]
        assert "shared_income_splits.member_id IN (7, 9)" in sql
        assert "group_members" not in sql

    @pytest.mark.asyncio
    async def test_a_zero_entitlement_is_not_income(self):
        # A split entitled to zero is a custodian who only COLLECTED the money and takes no share of
        # it. That is not their income — and without the filter it would show as a 0.00 row.
        assert "shared_income_splits.amount > 0" in (await _compile([7]))[0]

    @pytest.mark.asyncio
    async def test_the_page_is_ordered_by_scope_as_well_as_id(self):
        # Ids are unique per TABLE and this list spans two. Without the scope a private row and a
        # shared row sharing a date and an id have no total order, and Postgres may then return one on
        # two pages or on none.
        order_by = (await _compile([7], sort_by="amount"))[-1].split("ORDER BY")[1]
        assert "anon_1.amount ASC, anon_1.id DESC, anon_1.scope" in order_by

    @pytest.mark.asyncio
    async def test_every_filter_reaches_both_branches(self):
        # Written once and applied to each branch, so a filter added to the private list cannot
        # silently miss the shared one. Counted rather than merely present: one occurrence would mean
        # exactly that failure.
        sql = (await _compile([7], search="rent", category=IncomeCategory.rental_income, date_from=date(2026, 1, 1), date_to=date(2026, 6, 1)))[0]
        assert sql.count("'%rent%'") == 2
        assert sql.count("'rental_income'") == 2
        assert sql.count("'2026-01-01'") == 2
        assert sql.count("'2026-06-01'") == 2


# X2 on the flow lists: the rows come back grouped by scope, and the response says what each group is
# called and what it totals. The rule the whole surface rests on is that a scope selection FILTERS and
# is never a mode, so every section is on screen at once and no figure can be misread as the whole.
class TestScopeGrouping:
    @pytest.mark.asyncio
    async def test_the_page_is_ordered_scope_major_with_the_callers_sort_inside_it(self):
        # A section header can only be drawn where its rows are CONTIGUOUS, so the group has to lead
        # the ORDER BY and the caller's own sort has to apply within it. Without the leading term the
        # two scopes interleave and the same header is drawn several times down one page.
        order_by = (await _compile([7], sort_by="amount"))[-1].split("ORDER BY")[1]
        assert order_by.strip().startswith("anon_1.group_id NULLS FIRST")
        assert "anon_1.amount ASC" in order_by

    @pytest.mark.asyncio
    async def test_asking_for_only_private_builds_no_union(self):
        # Exactly the statement this list ran before the union existed.
        for sql in await _compile([7], scope=ListScope.private):
            assert "UNION" not in sql
            assert "shared_income_splits" not in sql

    @pytest.mark.asyncio
    async def test_asking_for_only_shared_reads_no_private_rows(self):
        for sql in await _compile([7], scope=ListScope.shared):
            assert "UNION" not in sql
            assert "income_entries" not in sql
            assert "shared_income_splits" in sql

    @pytest.mark.asyncio
    async def test_only_shared_with_no_seat_returns_nothing_rather_than_private_rows(self):
        # The trap this branch exists for: falling through to the private branch would answer "show me
        # only what the group earned" with the caller's own solo income. `IN ()` matches nothing, which
        # is the honest answer.
        for sql in await _compile([], scope=ListScope.shared):
            assert "income_entries" not in sql
            assert "shared_income_splits.member_id IN (NULL) AND (1 != 1)" in sql

    @pytest.mark.asyncio
    async def test_the_section_totals_run_over_the_same_filters_as_the_rows(self):
        # A filter that reached the rows and missed the aggregate would put a header above the rows it
        # does not describe. Both go through one _union, and this is what pins it.
        sql = await _compile_sums([7], search="rent", category=IncomeCategory.rental_income, date_from=date(2026, 1, 1))
        assert sql.count("'%rent%'") == 2
        assert sql.count("'rental_income'") == 2
        assert sql.count("'2026-01-01'") == 2
        assert "GROUP BY anon_1.group_id, anon_1.currency" in sql

    @pytest.mark.asyncio
    async def test_a_section_is_named_even_when_none_of_its_rows_are_on_this_page(self, monkeypatch):
        # The section keys are NOT a subset of the page's rows: a group whose income all sits on page
        # two still has a header to draw on page one, so its name has to be resolved from the sections
        # and not only from the rows.
        names = _wire(monkeypatch, [_row(group_id=3)], sums=[(3, "ARS", Decimal("40.00"), 1), (4, "ARS", Decimal("90.00"), 2)])
        result = await income_service.list_income(AsyncMock(spec=AsyncSession), USER)
        assert names.await_args.args[1] == [3, 4]
        assert [(s.group_id, s.group_name, s.count) for s in result.sections] == [(3, "Casa", 1), (4, "Viaje", 2)]

    @pytest.mark.asyncio
    async def test_a_section_totals_each_currency_on_its_own(self, monkeypatch):
        # Currencies never net, exactly as the group hub's balances do not: one blended figure would
        # hide which money was which, and a per-currency total needs no rate at all.
        _wire(monkeypatch, [_row(group_id=3)], sums=[(3, "USD", Decimal("40.00"), 1), (3, "ARS", Decimal("30.00"), 2)])
        result = await income_service.list_income(AsyncMock(spec=AsyncSession), USER)
        assert [(t.currency, t.amount) for t in result.sections[0].totals] == [("ARS", Decimal("30.00")), ("USD", Decimal("40.00"))]
        assert result.sections[0].count == 3

    @pytest.mark.asyncio
    async def test_the_callers_own_rows_sort_first_and_are_writable(self, monkeypatch):
        # Yours leads, and it is the only section whose rows this list may edit.
        _wire(monkeypatch, [_row()], sums=[(4, "ARS", Decimal("80.00"), 1), (None, "ARS", Decimal("10.00"), 1)])
        sections = (await income_service.list_income(AsyncMock(spec=AsyncSession), USER)).sections
        assert [(s.scope, s.can_write) for s in sections] == [(SCOPE_PRIVATE, True), (SCOPE_SHARED, False)]

    @pytest.mark.asyncio
    async def test_a_solo_user_gets_no_sections_and_pays_for_no_aggregate(self, monkeypatch):
        # Every user at launch. An empty `sections` is what tells the page to draw a flat table, and the
        # aggregate is not issued at all — this list must cost what it cost before X2.
        _wire(monkeypatch, [_row(scope=SCOPE_PRIVATE, group_id=None, full_amount=None, source="manual")], member_ids=[])
        result = await income_service.list_income(AsyncMock(spec=AsyncSession), USER)
        assert result.sections == []
        income_service.income_repository.sum_by_scope.assert_not_awaited()


class TestTheResponse:
    @pytest.mark.asyncio
    async def test_a_shared_row_carries_the_share_and_the_whole(self, monkeypatch):
        # `amount` is what the user is entitled to and `full_amount` what the group received, so a
        # reader can say "your 40 of 100" without a second request.
        _wire(monkeypatch, [_row()])
        item = (await income_service.list_income(AsyncMock(spec=AsyncSession), USER)).items[0]
        assert (item.scope, item.amount, item.full_amount, item.group_id, item.group_name) == (
            SCOPE_SHARED,
            Decimal("40.00"),
            Decimal("100.00"),
            3,
            "Casa",
        )

    @pytest.mark.asyncio
    async def test_a_private_row_states_no_group_and_no_whole(self, monkeypatch):
        # The two would be one figure twice, and a null says "there is no other party" plainly.
        _wire(monkeypatch, [_row(scope=SCOPE_PRIVATE, group_id=None, full_amount=None, source="manual")])
        item = (await income_service.list_income(AsyncMock(spec=AsyncSession), USER)).items[0]
        assert (item.scope, item.full_amount, item.group_id, item.group_name) == (SCOPE_PRIVATE, None, None, None)

    @pytest.mark.asyncio
    async def test_a_shared_row_names_nobody_elses_account(self, monkeypatch):
        # `account_id` identifies where the money LANDED, frequently another member's account or one a
        # pot holds, and a row describing your share should not carry it.
        _wire(monkeypatch, [_row()])
        assert (await income_service.list_income(AsyncMock(spec=AsyncSession), USER)).items[0].account_id is None

    @pytest.mark.asyncio
    async def test_the_group_name_comes_from_one_query_for_the_whole_page(self, monkeypatch):
        # Not one lookup per row — that is the N+1 a paginated list makes expensive.
        names = _wire(monkeypatch, [_row(id=1, group_id=3), _row(id=2, group_id=3), _row(id=3, group_id=4)])
        await income_service.list_income(AsyncMock(spec=AsyncSession), USER)
        assert names.await_count == 1
        assert names.await_args.args[1] == [3, 4]


def _row(**overrides) -> IncomeListRow:
    data = dict(
        scope=SCOPE_SHARED,
        id=5,
        date=date(2026, 6, 1),
        amount=Decimal("40.00"),
        currency="ARS",
        category=IncomeCategory.rental_income,
        notes="Rent",
        account_id=None,
        source=SOURCE_SHARED,
        reconciliation_id=None,
        account_reconciliation_id=None,
        created_at=datetime(2026, 6, 1, 12),
        updated_at=datetime(2026, 6, 1, 12),
        group_id=3,
        full_amount=Decimal("100.00"),
    )
    data.update(overrides)
    return IncomeListRow(**data)


# Wires the service's four reads. `sums` is the section aggregate's rows in build_sections' shape —
# (group_id, currency, amount, count) — and defaults to one bucket per group the page's rows name, so a
# test that does not care about sections still gets consistent ones.
def _wire(monkeypatch, rows: list[IncomeListRow], *, member_ids: list[int] | None = None, sums=None) -> AsyncMock:
    monkeypatch.setattr(income_service.group_repository, "list_active_member_ids", AsyncMock(return_value=[7] if member_ids is None else member_ids))
    monkeypatch.setattr(income_service.income_repository, "list_by_user_filtered", AsyncMock(return_value=(rows, len(rows))))
    if sums is None:
        sums = [(row.group_id, row.currency, row.amount, 1) for row in rows]
    monkeypatch.setattr(income_service.income_repository, "sum_by_scope", AsyncMock(return_value=sums))
    groups = [type("G", (), {"id": 3, "name": "Casa"})(), type("G", (), {"id": 4, "name": "Viaje"})()]
    names = AsyncMock(return_value=groups)
    monkeypatch.setattr(income_service.group_repository, "get_by_ids", names)
    return names
