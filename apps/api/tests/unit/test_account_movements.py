from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError
from app.domain.account_movement import MovementKind
from app.models.account import Account, AccountType
from app.models.user import User
from app.services import account_movement_service

# The per-account ledger. Persistence is mocked (AsyncMock) as in the sibling service tests, so what
# these cover is the SERVICE's contract: ownership, the running balance's anchoring and arithmetic,
# and the rule that a filtered view carries no running balance. The union SQL itself — the branch
# selection, the opening_date bound, the tie-break order — is only meaningful against a real
# database and is verified there instead (see the PR's live run); a mocked repository would happily
# return rows a wrong query never would.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _account(**overrides) -> Account:
    data = dict(
        id=7,
        user_id=1,
        name="Galicia",
        type=AccountType.bank,
        currency="ARS",
        opening_balance=Decimal("100000"),
        opening_date=date(2026, 7, 1),
        is_active=True,
    )
    data.update(overrides)
    return Account(**data)


# A repository row: the union's projection, which the service reads by attribute.
def _row(source_id: int, kind: MovementKind, day: int, amount: str, **overrides):
    data = dict(
        source_id=source_id,
        kind=kind.value,
        date=date(2026, 7, day),
        amount=Decimal(amount),
        category=None,
        counterparty=None,
        counterparty_amount=None,
        counterparty_currency=None,
        notes=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


# Wires the three repository calls and the balance the ledger anchors to.
def _wire(monkeypatch, *, rows, total=None, balance="100000", newer="0"):
    monkeypatch.setattr(account_movement_service.account_service, "get_account", AsyncMock(return_value=_account()))
    monkeypatch.setattr(
        account_movement_service.account_service,
        "get_account_balances",
        AsyncMock(return_value={7: Decimal(balance)}),
    )
    monkeypatch.setattr(account_movement_service.account_movement_repository, "list_movements", AsyncMock(return_value=rows))
    monkeypatch.setattr(
        account_movement_service.account_movement_repository,
        "count_movements",
        AsyncMock(return_value=total if total is not None else len(rows)),
    )
    sum_newer = AsyncMock(return_value=Decimal(newer))
    monkeypatch.setattr(account_movement_service.account_movement_repository, "sum_of_newer_movements", sum_newer)
    return sum_newer


class TestOwnership:
    @pytest.mark.asyncio
    async def test_another_users_account_raises_not_found(self, monkeypatch):
        monkeypatch.setattr(account_movement_service.account_service, "get_account", AsyncMock(side_effect=NotFoundError("Account not found.")))
        with pytest.raises(NotFoundError):
            await account_movement_service.list_account_movements(AsyncMock(), 7, USER)


class TestRunningBalance:
    @pytest.mark.asyncio
    async def test_first_row_carries_the_accounts_own_balance(self, monkeypatch):
        # The ledger must not compute a second answer for "what is this account worth" — the top row
        # is the number the accounts table shows, so the two surfaces cannot disagree.
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 10, "-2500")], balance="444700")
        movements, _, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert movements[0].balance_after == Decimal("444700")

    @pytest.mark.asyncio
    async def test_each_row_undoes_the_one_above_it(self, monkeypatch):
        _wire(
            monkeypatch,
            rows=[
                _row(1, MovementKind.expense, 20, "-2500"),
                _row(2, MovementKind.income, 15, "1000"),
                _row(3, MovementKind.transfer, 10, "-500"),
            ],
            balance="10000",
        )
        movements, _, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert [m.balance_after for m in movements] == [Decimal("10000"), Decimal("12500"), Decimal("11500")]

    @pytest.mark.asyncio
    async def test_walking_the_whole_ledger_down_lands_on_the_opening_balance(self, monkeypatch):
        # The invariant that catches a movement type missing from the union: anchoring alone would
        # still produce a self-consistent column, just one that no longer reaches opening_balance.
        rows = [
            _row(1, MovementKind.adjustment, 30, "-1500"),
            _row(2, MovementKind.income, 20, "200000"),
            _row(3, MovementKind.settlement, 15, "-8000"),
            _row(4, MovementKind.expense, 10, "-12000"),
        ]
        _wire(monkeypatch, rows=rows, balance="278500")
        movements, _, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        oldest = movements[-1]
        assert oldest.balance_after - oldest.amount == _account().opening_balance

    @pytest.mark.asyncio
    async def test_a_later_page_is_anchored_by_the_movements_above_it(self, monkeypatch):
        # Page 3's first row is not the account's balance — it is the balance minus everything newer,
        # which is the whole reason the repository exposes sum_of_newer_movements.
        sum_newer = _wire(monkeypatch, rows=[_row(9, MovementKind.expense, 5, "-100")], balance="10000", newer="3000")
        movements, _, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=3, page_size=4)
        assert movements[0].balance_after == Decimal("7000")
        assert sum_newer.await_args.kwargs["offset"] == 8

    @pytest.mark.asyncio
    async def test_first_page_skips_the_anchor_query(self, monkeypatch):
        sum_newer = _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 5, "-100")])
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=1, page_size=25)
        assert sum_newer.await_args.kwargs["offset"] == 0


class TestFilteredView:
    @pytest.mark.asyncio
    async def test_a_filter_withholds_the_running_balance(self, monkeypatch):
        # Under a filter each value would still be true, but consecutive rows would differ by amounts
        # the filter hides — so the column is withheld rather than made to look like broken arithmetic.
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 10, "-2500"), _row(2, MovementKind.expense, 5, "-100")])
        movements, _, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, kind=MovementKind.expense)
        assert [m.balance_after for m in movements] == [None, None]

    @pytest.mark.asyncio
    async def test_a_filter_never_asks_for_the_anchor(self, monkeypatch):
        sum_newer = _wire(monkeypatch, rows=[])
        balances = AsyncMock(return_value={})
        monkeypatch.setattr(account_movement_service.account_service, "get_account_balances", balances)
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER, kind=MovementKind.transfer)
        sum_newer.assert_not_awaited()
        balances.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_filter_reaches_both_repository_calls(self, monkeypatch):
        _wire(monkeypatch, rows=[])
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER, kind=MovementKind.settlement)
        assert account_movement_service.account_movement_repository.list_movements.await_args.kwargs["kind"] is MovementKind.settlement
        assert account_movement_service.account_movement_repository.count_movements.await_args.kwargs["kind"] is MovementKind.settlement


class TestRowMapping:
    @pytest.mark.asyncio
    async def test_carries_the_accounts_currency_not_a_per_row_one(self, monkeypatch):
        _wire(monkeypatch, rows=[])
        _, _, currency = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert currency == "ARS"

    @pytest.mark.asyncio
    async def test_transfer_row_keeps_the_other_sides_pair(self, monkeypatch):
        _wire(
            monkeypatch,
            rows=[
                _row(
                    1,
                    MovementKind.transfer,
                    25,
                    "-50000",
                    counterparty="Dolares",
                    counterparty_amount=Decimal("40"),
                    counterparty_currency="USD",
                )
            ],
        )
        movements, _, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert (movements[0].counterparty, movements[0].counterparty_amount, movements[0].counterparty_currency) == ("Dolares", Decimal("40"), "USD")

    @pytest.mark.asyncio
    async def test_total_is_the_unpaged_count(self, monkeypatch):
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 10, "-1")], total=97)
        _, total, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page_size=1)
        assert total == 97

    @pytest.mark.asyncio
    async def test_empty_ledger_returns_no_rows_and_no_error(self, monkeypatch):
        _wire(monkeypatch, rows=[])
        movements, total, _ = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert (movements, total) == ([], 0)
