from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import NotFoundError
from app.domain.account_movement import AccountMovement, MovementKind, MovementRow, MovementSource
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

# The source a kind comes from when a test doesn't care. `adjustment` has no single answer — it spans
# both entry tables — so a test about adjustments names the source it means.
_DEFAULT_SOURCE = {
    MovementKind.income: MovementSource.income,
    MovementKind.expense: MovementSource.expense,
    MovementKind.settlement: MovementSource.settlement,
    MovementKind.transfer: MovementSource.transfer,
    MovementKind.adjustment: MovementSource.expense,
}


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


# A repository row: the movement plus the running total the window function computed beside it
# (Σ amounts from the newest row through this one). `running_total` defaults to the row's own amount,
# which is what the newest row carries.
def _row(
    source_id: int,
    kind: MovementKind,
    day: int,
    amount: str,
    *,
    source: MovementSource | None = None,
    running_total: str | None = None,
    **overrides,
):
    fields = dict(
        source=source or _DEFAULT_SOURCE[kind],
        source_id=source_id,
        kind=kind,
        date=date(2026, 7, day),
        amount=Decimal(amount),
    )
    fields.update(overrides)
    return MovementRow(
        movement=AccountMovement(**fields),
        running_total=Decimal(running_total if running_total is not None else amount),
    )


# Wires the three repository calls and the balance the ledger anchors to.
def _wire(monkeypatch, *, rows, total=None, balance="100000", empty_first_call=False, account=None):
    monkeypatch.setattr(account_movement_service.account_service, "get_account_in_scope", AsyncMock(return_value=account or _account()))
    balance_mock = AsyncMock(return_value=Decimal(balance))
    monkeypatch.setattr(account_movement_service.account_service, "get_account_balance", balance_mock)
    reported = total if total is not None else len(rows)
    # `empty_first_call` reproduces a page past the end: the repository returns nothing, the service
    # asks for a count, clamps, and re-asks.
    returns = [([], 0), (rows, reported)] if empty_first_call else [(rows, reported)]
    listing = AsyncMock(side_effect=returns * 4)
    monkeypatch.setattr(account_movement_service.account_movement_repository, "list_movements", listing)
    monkeypatch.setattr(
        account_movement_service.account_movement_repository,
        "count_movements",
        AsyncMock(return_value=reported),
    )
    return balance_mock


class TestOwnership:
    @pytest.mark.asyncio
    async def test_an_unreachable_account_raises_not_found(self, monkeypatch):
        monkeypatch.setattr(
            account_movement_service.account_service, "get_account_in_scope", AsyncMock(side_effect=NotFoundError("Account not found."))
        )
        with pytest.raises(NotFoundError):
            await account_movement_service.list_account_movements(AsyncMock(), 7, USER)

    @pytest.mark.asyncio
    async def test_the_account_is_loaded_in_either_scope_and_its_pot_reaches_the_query(self, monkeypatch):
        # A group's bank account has a ledger worth reading, and `transfers` is the one movement table
        # carrying a scope of its own — so the pot has to reach the query or a transfer between two of
        # the pot's accounts moves the balance and never appears in the ledger explaining it.
        _wire(monkeypatch, rows=[_row(1, MovementKind.transfer, 10, "3000")], account=_account(user_id=None, pot_id=4))
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert account_movement_service.account_movement_repository.list_movements.await_args.kwargs["pot_id"] == 4

    @pytest.mark.asyncio
    async def test_a_private_account_passes_no_pot(self, monkeypatch):
        _wire(monkeypatch, rows=[_row(1, MovementKind.transfer, 10, "3000")])
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert account_movement_service.account_movement_repository.list_movements.await_args.kwargs["pot_id"] is None


class TestRunningBalance:
    @pytest.mark.asyncio
    async def test_first_row_carries_the_accounts_own_balance(self, monkeypatch):
        # The ledger must not compute a second answer for "what is this account worth" — the top row
        # is the number the accounts table shows, so the two surfaces cannot disagree.
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 10, "-2500")], balance="444700")
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert response.items[0].balance_after == Decimal("444700")

    @pytest.mark.asyncio
    async def test_each_row_undoes_the_one_above_it(self, monkeypatch):
        # running_total is cumulative from the newest row, which is what the window function emits.
        _wire(
            monkeypatch,
            rows=[
                _row(1, MovementKind.expense, 20, "-2500", running_total="-2500"),
                _row(2, MovementKind.income, 15, "1000", running_total="-1500"),
                _row(3, MovementKind.transfer, 10, "-500", running_total="-2000"),
            ],
            balance="10000",
        )
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert [m.balance_after for m in response.items] == [Decimal("10000"), Decimal("12500"), Decimal("11500")]

    @pytest.mark.asyncio
    async def test_walking_the_whole_ledger_down_lands_on_the_opening_balance(self, monkeypatch):
        # Anchoring alone cannot catch a movement type missing from the union — it would still produce
        # a self-consistent column, just one that no longer reaches opening_balance. This pins the
        # arithmetic; that the union's row set still MATCHES the balance path is asserted against a
        # real database in tests/integration/test_account_ledger_drift.py.
        _wire(
            monkeypatch,
            rows=[
                _row(1, MovementKind.adjustment, 30, "-1500", running_total="-1500"),
                _row(2, MovementKind.income, 20, "200000", running_total="198500"),
                _row(3, MovementKind.settlement, 15, "-8000", running_total="190500"),
                _row(4, MovementKind.expense, 10, "-12000", running_total="178500"),
            ],
            balance="278500",
        )
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        oldest = response.items[-1]
        assert oldest.balance_after - oldest.amount == _account().opening_balance

    @pytest.mark.asyncio
    async def test_a_later_page_is_anchored_by_the_movements_above_it(self, monkeypatch):
        # Page 3's first row is not the account's balance — the window's running_total already
        # accounts for everything newer, including the rows on the pages above.
        _wire(monkeypatch, rows=[_row(9, MovementKind.expense, 5, "-100", running_total="-3100")], total=12, balance="10000")
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=3, page_size=4)
        assert response.items[0].balance_after == Decimal("13000")

    @pytest.mark.asyncio
    async def test_one_pass_serves_an_in_range_page(self, monkeypatch):
        # The total rides on the page query, so an in-range page must not also ask for a count.
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 5, "-100")], total=30)
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=1, page_size=25)
        account_movement_service.account_movement_repository.count_movements.assert_not_awaited()


class TestPageClamping:
    @pytest.mark.asyncio
    async def test_a_page_past_the_end_is_clamped_to_the_last_one(self, monkeypatch):
        # A stale bookmark, or entries deleted while the user sat on a later page, would otherwise
        # render "no movements yet" beneath a header showing a non-zero balance, with no page marked
        # active in the pager. Clamping also keeps OFFSET bounded — Python ints are unbounded, and a
        # large enough page overflows the int64 bind parameter with a 500 rather than a 422.
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 5, "-100")], total=30, empty_first_call=True)
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=10**20, page_size=25)
        assert response.page == 2
        listing = account_movement_service.account_movement_repository.list_movements
        assert listing.await_args.kwargs["page"] == 2
        # The FIRST attempt must already be bounded: it is what builds the OFFSET, and an unbounded
        # page reaches Postgres as a bind outside int64 and 500s before any clamp can run. A mocked
        # repository cannot overflow, so this asserts the ceiling rather than the symptom.
        assert listing.await_args_list[0].kwargs["page"] <= account_movement_service._MAX_PAGE

    @pytest.mark.asyncio
    async def test_an_empty_ledger_stays_on_page_one(self, monkeypatch):
        _wire(monkeypatch, rows=[], total=0)
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=4)
        assert (response.page, response.total, response.items) == (1, 0, [])

    @pytest.mark.asyncio
    async def test_a_page_within_range_is_left_alone(self, monkeypatch):
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 5, "-100")], total=30)
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page=2, page_size=25)
        assert response.page == 2


class TestFilteredView:
    @pytest.mark.asyncio
    async def test_a_filter_withholds_the_running_balance(self, monkeypatch):
        # Under a filter each value would still be true, but consecutive rows would differ by amounts
        # the filter hides — so the column is withheld rather than made to look like broken arithmetic.
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 10, "-2500"), _row(2, MovementKind.expense, 5, "-100")])
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, kind=MovementKind.expense)
        assert [m.balance_after for m in response.items] == [None, None]

    @pytest.mark.asyncio
    async def test_a_filter_never_asks_for_the_anchor(self, monkeypatch):
        balance = _wire(monkeypatch, rows=[_row(1, MovementKind.transfer, 5, "-100")])
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER, kind=MovementKind.transfer)
        balance.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_filter_reaches_both_repository_calls(self, monkeypatch):
        _wire(monkeypatch, rows=[_row(1, MovementKind.settlement, 5, "-100")])
        await account_movement_service.list_account_movements(AsyncMock(), 7, USER, kind=MovementKind.settlement)
        listing = account_movement_service.account_movement_repository.list_movements.await_args.kwargs
        assert listing["kind"] is MovementKind.settlement
        # The opening_date bound travels with the query instead of being re-joined per branch.
        assert listing["opening_date"] == _account().opening_date


class TestRowMapping:
    @pytest.mark.asyncio
    async def test_carries_the_accounts_currency_not_a_per_row_one(self, monkeypatch):
        _wire(monkeypatch, rows=[])
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert response.currency == "ARS"

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
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert (response.items[0].counterparty, response.items[0].counterparty_amount, response.items[0].counterparty_currency) == (
            "Dolares",
            Decimal("40"),
            "USD",
        )

    @pytest.mark.asyncio
    async def test_total_is_the_unpaged_count(self, monkeypatch):
        _wire(monkeypatch, rows=[_row(1, MovementKind.expense, 10, "-1")], total=97)
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER, page_size=1)
        assert response.total == 97

    @pytest.mark.asyncio
    async def test_empty_ledger_returns_no_rows_and_no_error(self, monkeypatch):
        _wire(monkeypatch, rows=[])
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert (response.items, response.total) == ([], 0)


class TestRowIdentity:
    @pytest.mark.asyncio
    async def test_two_adjustments_sharing_an_id_stay_distinguishable(self, monkeypatch):
        # income_entries and expense_entries have independent id sequences, so a reconciliation that
        # posted an income adjustment and one that posted an expense adjustment can both be id 30.
        # `kind` is 'adjustment' for both, so only `source` tells them apart — which is what the
        # ledger's React key is built from.
        _wire(
            monkeypatch,
            rows=[
                _row(30, MovementKind.adjustment, 12, "-1500", source=MovementSource.expense),
                _row(30, MovementKind.adjustment, 12, "700", source=MovementSource.income),
            ],
        )
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        keys = [(m.source, m.source_id) for m in response.items]
        assert len(set(keys)) == 2
        assert len({(m.kind, m.source_id) for m in response.items}) == 1

    @pytest.mark.asyncio
    async def test_source_survives_the_mapping(self, monkeypatch):
        _wire(monkeypatch, rows=[_row(4, MovementKind.settlement, 15, "-8000")])
        response = await account_movement_service.list_account_movements(AsyncMock(), 7, USER)
        assert response.items[0].source is MovementSource.settlement
