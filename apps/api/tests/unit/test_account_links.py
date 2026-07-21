from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain import AccountCurrencyMismatchError, NotFoundError
from app.models.account import Account, AccountType
from app.models.user import User
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services import account_service

# Money-linking (PR 2): an expense / income / settlement may carry an optional account_id.
# validate_account_link enforces ownership + currency-match (a cash balance stays exact), and the
# balance is the query-time union opening + income − expenses − settlements. Persistence is mocked.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


def _account(**overrides) -> Account:
    data = dict(id=7, user_id=1, name="Caja $", type=AccountType.bank, currency="ARS", opening_balance=Decimal("1000"), opening_date=date(2026, 1, 1))
    data.update(overrides)
    return Account(**data)


class TestValidateAccountLink:
    @pytest.mark.asyncio
    async def test_none_is_noop(self):
        # No repo call, no raise — an unlinked entry is always allowed.
        await account_service.validate_account_link(AsyncMock(), USER, None, "ARS")

    @pytest.mark.asyncio
    async def test_missing_account_raises_not_found(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await account_service.validate_account_link(AsyncMock(), USER, 7, "ARS")

    @pytest.mark.asyncio
    async def test_currency_mismatch_raises(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        with pytest.raises(AccountCurrencyMismatchError):
            await account_service.validate_account_link(AsyncMock(), USER, 7, "USD")

    @pytest.mark.asyncio
    async def test_matching_currency_ok(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        await account_service.validate_account_link(AsyncMock(), USER, 7, "ARS")


class TestBalanceUnion:
    @pytest.mark.asyncio
    async def test_balance_is_opening_plus_income_minus_expenses_and_settlements(self, monkeypatch):
        account = _account(id=7, opening_balance=Decimal("1000"))
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("500")}))
        monkeypatch.setattr(account_service.expense_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("200")}))
        monkeypatch.setattr(account_service.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("50")}))

        balances = await account_service.get_account_balances(AsyncMock(), [account], USER.id)

        # 1000 + 500 − 200 − 50 = 1250.
        assert balances == {7: Decimal("1250")}

    @pytest.mark.asyncio
    async def test_no_linked_rows_is_opening_balance(self, monkeypatch):
        account = _account(id=7, opening_balance=Decimal("1000"))
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.expense_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))

        balances = await account_service.get_account_balances(AsyncMock(), [account], USER.id)

        assert balances == {7: Decimal("1000")}

    @pytest.mark.asyncio
    async def test_empty_accounts_short_circuits(self):
        # No repo calls when there are no accounts.
        assert await account_service.get_account_balances(AsyncMock(), [], USER.id) == {}


class TestExpenseAccountPairingSchema:
    def test_account_on_card_expense_rejected(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(date=date(2026, 1, 1), amount=Decimal("10"), currency="ARS", payment_method="credit_card", account_id=7)

    def test_account_on_cash_expense_ok(self):
        body = ExpenseCreate(date=date(2026, 1, 1), amount=Decimal("10"), currency="ARS", payment_method="cash", account_id=7)
        assert body.account_id == 7

    def test_update_account_on_card_rejected_when_both_provided(self):
        with pytest.raises(ValidationError):
            ExpenseUpdate(payment_method="credit_card", account_id=7)
