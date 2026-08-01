from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    AccountReconciliationBeforeLastError,
    AccountReconciliationBeforeOpeningError,
    AccountReconciliationFutureDateError,
    AccountReconciliationNotLatestError,
    NotFoundError,
)
from app.models.account import Account, AccountType
from app.models.account_reconciliation import AccountReconciliation
from app.models.expense_entry import ExpenseCategory
from app.models.income_entry import IncomeCategory
from app.models.user import User
from app.services import account_reconciliation_service as svc

# Account reconciliation is the point-in-time Option-F true-up: the derived balance at a date is
# compared with the real balance the user read, and the gap becomes exactly one dated adjustment
# entry linked to the account. Persistence is mocked (AsyncMock), matching the other service tests.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)
TODAY = date(2026, 7, 29)


def _reconciliation(**overrides) -> AccountReconciliation:
    data = dict(
        id=42,
        user_id=1,
        account_id=7,
        as_of_date=TODAY,
        statement_balance=Decimal("800"),
        computed_balance=Decimal("1000"),
        difference=Decimal("-200"),
    )
    data.update(overrides)
    return AccountReconciliation(**data)


def _account(**overrides) -> Account:
    data = dict(
        id=7,
        user_id=1,
        name="Caja de ahorro $",
        type=AccountType.bank,
        currency="ARS",
        opening_balance=Decimal("1000"),
        opening_date=date(2026, 1, 1),
        is_active=True,
    )
    data.update(overrides)
    return Account(**data)


# Wires the whole create_reconciliation dependency set: a fixed account, a fixed "today", the five
# balance sums (income, expenses, settlements, and both transfer legs), and capture-and-assign-id fakes
# for the rows the service writes.
def _wire(
    monkeypatch,
    account: Account,
    *,
    income=None,
    expenses=None,
    settlements=None,
    transfers_in=None,
    transfers_out=None,
    today: date = TODAY,
    last_reconciled: date | None = None,
) -> dict:
    captured: dict = {}
    monkeypatch.setattr(svc.account_service, "get_account", AsyncMock(return_value=account))
    monkeypatch.setattr(svc.settings_service, "get_user_today", AsyncMock(return_value=today))
    monkeypatch.setattr(svc.income_repository, "sum_by_account_ids", AsyncMock(return_value=income or {}))
    monkeypatch.setattr(svc.expense_repository, "sum_by_account_ids", AsyncMock(return_value=expenses or {}))
    monkeypatch.setattr(svc.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value=settlements or {}))
    monkeypatch.setattr(svc.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value=transfers_in or {}))
    monkeypatch.setattr(svc.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value=transfers_out or {}))
    monkeypatch.setattr(
        svc.account_reconciliation_repository,
        "get_latest_dates_by_account_ids",
        AsyncMock(return_value={account.id: last_reconciled} if last_reconciled else {}),
    )

    async def fake_create_reconciliation(_session, reconciliation):
        reconciliation.id = 42
        captured["reconciliation"] = reconciliation
        return reconciliation

    async def fake_create_income(_session, entry):
        entry.id = 91
        captured["income"] = entry
        return entry

    async def fake_create_expense(_session, entry):
        entry.id = 92
        captured["expense"] = entry
        return entry

    monkeypatch.setattr(svc.account_reconciliation_repository, "create", fake_create_reconciliation)
    monkeypatch.setattr(svc.account_reconciliation_repository, "save", AsyncMock())
    monkeypatch.setattr(svc.income_repository, "create", fake_create_income)
    monkeypatch.setattr(svc.expense_repository, "create", fake_create_expense)
    return captured


class TestDifference:
    def test_positive_when_real_balance_is_higher(self):
        assert svc.compute_reconciliation_difference(Decimal("1500"), Decimal("1200")) == Decimal("300")

    def test_negative_when_real_balance_is_lower(self):
        assert svc.compute_reconciliation_difference(Decimal("800"), Decimal("1200")) == Decimal("-400")

    def test_zero_when_already_true(self):
        assert svc.compute_reconciliation_difference(Decimal("1200"), Decimal("1200")) == Decimal(0)


class TestComputeBalanceAt:
    @pytest.mark.asyncio
    async def test_unions_opening_income_expenses_and_settlements(self, monkeypatch):
        monkeypatch.setattr(svc.income_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("500")}))
        monkeypatch.setattr(svc.expense_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("300")}))
        monkeypatch.setattr(svc.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("150")}))
        monkeypatch.setattr(svc.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(), date(2026, 6, 30))

        assert balance == Decimal("1050")  # 1000 + 500 - 300 - 150

    @pytest.mark.asyncio
    async def test_opening_balance_excluded_before_the_account_opened(self, monkeypatch):
        monkeypatch.setattr(svc.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(opening_date=date(2026, 5, 1)), date(2026, 4, 30))

        assert balance == Decimal(0)

    @pytest.mark.asyncio
    async def test_sums_are_bounded_by_the_as_of_date(self, monkeypatch):
        # All THREE sums must carry the bound — a missing one would silently include rows dated
        # after as_of_date, so the recorded computed_balance would not be a point-in-time figure.
        income = AsyncMock(return_value={})
        expenses = AsyncMock(return_value={})
        settlements = AsyncMock(return_value={})
        monkeypatch.setattr(svc.income_repository, "sum_by_account_ids", income)
        monkeypatch.setattr(svc.expense_repository, "sum_by_account_ids", expenses)
        monkeypatch.setattr(svc.card_settlement_repository, "sum_by_account_ids", settlements)
        monkeypatch.setattr(svc.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))

        await svc.compute_account_balance_at(AsyncMock(), _account(), date(2026, 6, 30))

        for mock in (income, expenses, settlements):
            assert mock.await_args.kwargs["as_of_date"] == date(2026, 6, 30)

    @pytest.mark.asyncio
    async def test_opening_balance_included_on_the_opening_date_itself(self, monkeypatch):
        # The boundary: the guard is `opening_date <= as_of_date`, so the opening date counts.
        monkeypatch.setattr(svc.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(opening_date=date(2026, 5, 1)), date(2026, 5, 1))

        assert balance == Decimal("1000")

    @pytest.mark.asyncio
    async def test_balance_can_be_negative(self, monkeypatch):
        monkeypatch.setattr(svc.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.expense_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("2500")}))
        monkeypatch.setattr(svc.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_in_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(svc.transfer_repository, "sum_out_by_account_ids", AsyncMock(return_value={}))

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(), TODAY)

        assert balance == Decimal("-1500")


class TestCreateReconciliation:
    @pytest.mark.asyncio
    async def test_shortfall_creates_an_adjustment_expense(self, monkeypatch):
        captured = _wire(monkeypatch, _account())
        session = AsyncMock()

        reconciliation = await svc.create_reconciliation(session, 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("800"))

        assert reconciliation.difference == Decimal("-200")
        expense = captured["expense"]
        assert expense.amount == Decimal("200")
        assert expense.category == ExpenseCategory.account_adjustment
        assert expense.account_id == 7
        assert expense.currency == "ARS"
        assert expense.date == date(2026, 7, 20)
        assert expense.source == "reconciliation"
        assert expense.account_reconciliation_id == 42
        # A true-up is not a payment, so it carries no payment method (and could not carry a card one).
        assert expense.payment_method is None
        assert reconciliation.adjustment_expense_id == 92
        assert "income" not in captured
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_surplus_creates_an_adjustment_income(self, monkeypatch):
        captured = _wire(monkeypatch, _account())
        session = AsyncMock()

        reconciliation = await svc.create_reconciliation(session, 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("1250"))

        assert reconciliation.difference == Decimal("250")
        income = captured["income"]
        assert income.amount == Decimal("250")
        assert income.category == IncomeCategory.account_adjustment
        assert income.account_id == 7
        assert income.account_reconciliation_id == 42
        assert reconciliation.adjustment_income_id == 91
        assert "expense" not in captured
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_matching_balance_creates_no_adjustment(self, monkeypatch):
        captured = _wire(monkeypatch, _account())
        session = AsyncMock()

        reconciliation = await svc.create_reconciliation(session, 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("1000"))

        assert reconciliation.difference == Decimal(0)
        assert reconciliation.adjustment_expense_id is None
        assert reconciliation.adjustment_income_id is None
        assert "expense" not in captured and "income" not in captured
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reconciling_today_is_allowed(self, monkeypatch):
        _wire(monkeypatch, _account())
        reconciliation = await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("1000"))
        assert reconciliation.as_of_date == TODAY

    @pytest.mark.asyncio
    async def test_future_date_is_rejected(self, monkeypatch):
        _wire(monkeypatch, _account())
        with pytest.raises(AccountReconciliationFutureDateError):
            await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 30), statement_balance=Decimal("1000"))

    @pytest.mark.asyncio
    async def test_date_before_the_opening_date_is_rejected(self, monkeypatch):
        _wire(monkeypatch, _account(opening_date=date(2026, 3, 1)))
        with pytest.raises(AccountReconciliationBeforeOpeningError):
            await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 2, 28), statement_balance=Decimal("1000"))

    @pytest.mark.asyncio
    async def test_adjustment_takes_the_accounts_currency(self, monkeypatch):
        captured = _wire(monkeypatch, _account(currency="USD"))
        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("1200"))
        assert captured["income"].currency == "USD"

    @pytest.mark.asyncio
    async def test_re_reconciling_the_same_date_is_self_correcting(self, monkeypatch):
        # After the first true-up the adjustment is part of the derived balance, so a second
        # reconciliation with the same real balance finds no gap and posts nothing.
        captured = _wire(monkeypatch, _account(), income={7: Decimal("250")}, last_reconciled=date(2026, 7, 20))
        reconciliation = await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("1250"))
        assert reconciliation.difference == Decimal(0)
        assert "expense" not in captured and "income" not in captured

    @pytest.mark.asyncio
    async def test_every_written_row_carries_the_callers_user_id(self, monkeypatch):
        # The cross-tenant invariant: nothing is written under another user's id.
        captured = _wire(monkeypatch, _account())
        reconciliation = await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("1250"))
        assert reconciliation.user_id == USER.id
        assert captured["income"].user_id == USER.id

        captured = _wire(monkeypatch, _account())
        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("800"))
        assert captured["expense"].user_id == USER.id

    @pytest.mark.asyncio
    async def test_ownership_is_checked_before_anything_is_written(self, monkeypatch):
        captured = _wire(monkeypatch, _account())
        monkeypatch.setattr(svc.account_service, "get_account", AsyncMock(side_effect=NotFoundError("Account not found.")))
        session = AsyncMock()

        with pytest.raises(NotFoundError):
            await svc.create_reconciliation(session, 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("800"))

        assert captured == {}
        session.commit.assert_not_awaited()


class TestOutOfOrderGuard:
    # Reconciliations are point-in-time truths applied forward. An older one entered afterwards would
    # post its adjustment underneath the newer one — whose date bound cannot see it — so the newer,
    # authoritative balance would silently stop matching what the user attested to.
    @pytest.mark.asyncio
    async def test_date_before_the_latest_reconciliation_is_rejected(self, monkeypatch):
        _wire(monkeypatch, _account(), last_reconciled=date(2026, 7, 20))
        with pytest.raises(AccountReconciliationBeforeLastError) as exc:
            await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 10), statement_balance=Decimal("950"))
        assert exc.value.extra == {"last_reconciled_date": "2026-07-20"}

    @pytest.mark.asyncio
    async def test_nothing_is_written_when_the_date_is_rejected(self, monkeypatch):
        captured = _wire(monkeypatch, _account(), last_reconciled=date(2026, 7, 20))
        session = AsyncMock()
        with pytest.raises(AccountReconciliationBeforeLastError):
            await svc.create_reconciliation(session, 7, USER, as_of_date=date(2026, 7, 10), statement_balance=Decimal("950"))
        assert captured == {}
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_same_date_as_the_latest_is_allowed(self, monkeypatch):
        # The boundary — re-running the latest date is the self-correcting path, not an out-of-order one.
        _wire(monkeypatch, _account(), last_reconciled=date(2026, 7, 20))
        reconciliation = await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 20), statement_balance=Decimal("1250"))
        assert reconciliation.as_of_date == date(2026, 7, 20)

    @pytest.mark.asyncio
    async def test_a_later_date_is_allowed(self, monkeypatch):
        _wire(monkeypatch, _account(), last_reconciled=date(2026, 7, 20))
        reconciliation = await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 25), statement_balance=Decimal("1250"))
        assert reconciliation.as_of_date == date(2026, 7, 25)

    @pytest.mark.asyncio
    async def test_a_never_reconciled_account_accepts_any_valid_date(self, monkeypatch):
        _wire(monkeypatch, _account())
        reconciliation = await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 1, 15), statement_balance=Decimal("1250"))
        assert reconciliation.as_of_date == date(2026, 1, 15)


class TestReadAndDelete:
    @pytest.mark.asyncio
    async def test_list_verifies_account_ownership(self, monkeypatch):
        monkeypatch.setattr(svc.account_service, "get_account", AsyncMock(side_effect=NotFoundError("Account not found.")))
        with pytest.raises(NotFoundError):
            await svc.list_reconciliations(AsyncMock(), 7, USER)

    @pytest.mark.asyncio
    async def test_get_raises_when_the_reconciliation_is_missing(self, monkeypatch):
        monkeypatch.setattr(svc.account_service, "get_account", AsyncMock(return_value=_account()))
        monkeypatch.setattr(svc.account_reconciliation_repository, "get_by_id", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await svc.get_reconciliation(AsyncMock(), 7, 42, USER)

    @pytest.mark.asyncio
    async def test_delete_commits_once(self, monkeypatch):
        # get_reconciliation is deliberately NOT stubbed, so the real ownership chain runs:
        # account_service.get_account (user-scoped) then get_by_id scoped to the account.
        row = _reconciliation(as_of_date=date(2026, 7, 20))
        monkeypatch.setattr(svc.account_service, "get_account", AsyncMock(return_value=_account()))
        get_by_id = AsyncMock(return_value=row)
        monkeypatch.setattr(svc.account_reconciliation_repository, "get_by_id", get_by_id)
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_latest_dates_by_account_ids",
            AsyncMock(return_value={7: date(2026, 7, 20)}),
        )
        delete_mock = AsyncMock()
        monkeypatch.setattr(svc.account_reconciliation_repository, "delete", delete_mock)
        session = AsyncMock()

        await svc.delete_reconciliation(session, 7, 42, USER)

        # Scoped to BOTH the reconciliation id and the account id — another account's rid can't match.
        assert get_by_id.await_args.args[1:] == (42, 7)
        delete_mock.assert_awaited_once()
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_is_refused_when_a_later_reconciliation_exists(self, monkeypatch):
        # An older adjustment is already inside every later reconciliation's recorded
        # computed_balance, so removing it would silently skew those. Delete newest-first.
        monkeypatch.setattr(svc.account_service, "get_account", AsyncMock(return_value=_account()))
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_by_id",
            AsyncMock(return_value=_reconciliation(as_of_date=date(2026, 7, 10))),
        )
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_latest_dates_by_account_ids",
            AsyncMock(return_value={7: date(2026, 7, 20)}),
        )
        delete_mock = AsyncMock()
        monkeypatch.setattr(svc.account_reconciliation_repository, "delete", delete_mock)
        session = AsyncMock()

        with pytest.raises(AccountReconciliationNotLatestError) as exc:
            await svc.delete_reconciliation(session, 7, 42, USER)

        assert exc.value.extra == {"last_reconciled_date": "2026-07-20"}
        delete_mock.assert_not_awaited()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_latest_reconciled_dates_skips_accounts_without_ids(self, monkeypatch):
        latest = AsyncMock(return_value={7: date(2026, 7, 20)})
        monkeypatch.setattr(svc.account_reconciliation_repository, "get_latest_dates_by_account_ids", latest)

        result = await svc.get_latest_reconciled_dates(AsyncMock(), [_account(), _account(id=None)], 1)

        assert result == {7: date(2026, 7, 20)}
        assert latest.await_args.args[1] == [7]
