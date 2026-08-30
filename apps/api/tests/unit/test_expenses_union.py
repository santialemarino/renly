from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.expense_entry import ExpenseCategory
from app.models.user import User
from app.repositories import expense_repository
from app.repositories.expense_repository import SCOPE_PRIVATE, SCOPE_SHARED, SOURCE_SHARED, ExpenseListRow
from app.services import expense_service

# The /expenses union (D18/D21): the user's own rows and their SHARE of every shared expense, as one
# list. The rows it actually returns are proved against a real database in tests/integration; these pin
# the two things reachable without one — the statement's shape, and how a row becomes a response.

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
    await expense_repository.list_by_user_filtered(session, USER.id, member_ids, **kwargs)
    return session.statements


class TestTheStatementShape:
    @pytest.mark.asyncio
    async def test_a_user_in_no_group_gets_no_union_at_all(self):
        # Every user at launch is in no group, and /expenses is the most-used page in the app. Building
        # a union whose second branch can only ever be empty would make all of them pay for a feature
        # they do not have.
        for sql in await _compile([]):
            assert "shared_expense_splits" not in sql
            assert "UNION" not in sql

    @pytest.mark.asyncio
    async def test_a_member_gets_both_branches(self):
        for sql in await _compile([7]):
            assert "UNION ALL" in sql
            assert "expense_entries" in sql and "shared_expense_splits" in sql

    @pytest.mark.asyncio
    async def test_the_shared_branch_is_keyed_on_the_callers_own_seats(self):
        # An IN over the seats, not a join to group_members: the join makes Postgres scan every split
        # in the database, and the seats are resolved by the service anyway.
        sql = (await _compile([7, 9]))[0]
        assert "shared_expense_splits.member_id IN (7, 9)" in sql
        assert "group_members" not in sql

    @pytest.mark.asyncio
    async def test_a_zero_share_is_not_spending(self):
        # A split of zero is a payer who took no part (D33). It is not spending, so it does not belong
        # in a spending list — and without the filter it would show as a 0.00 row on every page.
        assert "shared_expense_splits.amount > 0" in (await _compile([7]))[0]

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
        sql = (
            await _compile(
                [7], search="taxi", category=ExpenseCategory.transport, payment_method="cash", date_from=date(2026, 1, 1), date_to=date(2026, 6, 1)
            )
        )[0]
        assert sql.count("'%taxi%'") == 2
        assert sql.count("'transport'") == 2
        assert sql.count("'cash'") == 2
        assert sql.count("'2026-01-01'") == 2
        assert sql.count("'2026-06-01'") == 2


def _row(**overrides) -> ExpenseListRow:
    data = dict(
        scope=SCOPE_SHARED,
        id=5,
        date=date(2026, 6, 1),
        amount=Decimal("30.00"),
        currency="ARS",
        category=ExpenseCategory.dining,
        notes="Dinner",
        payment_method="cash",
        credit_card_id=None,
        account_id=None,
        source=SOURCE_SHARED,
        payment_obligation_id=None,
        subscription_id=None,
        installment_id=None,
        reconciliation_id=None,
        account_reconciliation_id=None,
        created_at=datetime(2026, 6, 1, 12),
        updated_at=datetime(2026, 6, 1, 12),
        group_id=3,
        full_amount=Decimal("90.00"),
    )
    data.update(overrides)
    return ExpenseListRow(**data)


class TestTheResponse:
    @pytest.mark.asyncio
    async def test_a_shared_row_carries_the_share_and_the_whole(self, monkeypatch):
        # `amount` is what the user spent (D2) and `full_amount` what the group did, so a reader can
        # say "your 30 of 90" without a second request.
        _wire(monkeypatch, [_row()])
        result = await expense_service.list_expenses(AsyncMock(spec=AsyncSession), USER)
        item = result.items[0]
        assert (item.scope, item.amount, item.full_amount, item.group_id, item.group_name) == (
            SCOPE_SHARED,
            Decimal("30.00"),
            Decimal("90.00"),
            3,
            "Casa",
        )

    @pytest.mark.asyncio
    async def test_a_private_row_states_no_group_and_no_whole(self, monkeypatch):
        # The two would be one figure twice, and a null says "there is no other party" plainly.
        _wire(monkeypatch, [_row(scope=SCOPE_PRIVATE, group_id=None, full_amount=None, source="manual")])
        result = await expense_service.list_expenses(AsyncMock(spec=AsyncSession), USER)
        item = result.items[0]
        assert (item.scope, item.full_amount, item.group_id, item.group_name) == (SCOPE_PRIVATE, None, None, None)

    @pytest.mark.asyncio
    async def test_a_shared_row_names_nobody_elses_card_or_account(self, monkeypatch):
        # Those identify the PAYER's instrument, frequently another member's. `payment_method` is kept
        # because it describes the expense rather than naming anyone's account.
        _wire(monkeypatch, [_row()])
        item = (await expense_service.list_expenses(AsyncMock(spec=AsyncSession), USER)).items[0]
        assert (item.account_id, item.credit_card_id, item.payment_method) == (None, None, "cash")

    @pytest.mark.asyncio
    async def test_the_group_name_comes_from_one_query_for_the_whole_page(self, monkeypatch):
        # Not one lookup per row — that is the N+1 a paginated list makes expensive.
        names = _wire(monkeypatch, [_row(id=1, group_id=3), _row(id=2, group_id=3), _row(id=3, group_id=4)])
        await expense_service.list_expenses(AsyncMock(spec=AsyncSession), USER)
        assert names.await_count == 1
        assert names.await_args.args[1] == [3, 4]


def _wire(monkeypatch, rows: list[ExpenseListRow]) -> AsyncMock:
    monkeypatch.setattr(expense_service.group_repository, "list_active_member_ids", AsyncMock(return_value=[7]))
    monkeypatch.setattr(expense_service.expense_repository, "list_by_user_filtered", AsyncMock(return_value=(rows, len(rows))))
    groups = [type("G", (), {"id": 3, "name": "Casa"})(), type("G", (), {"id": 4, "name": "Viaje"})()]
    names = AsyncMock(return_value=groups)
    monkeypatch.setattr(expense_service.group_repository, "get_by_ids", names)
    return names
