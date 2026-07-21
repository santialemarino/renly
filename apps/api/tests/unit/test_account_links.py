from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain import (
    AccountCardExclusivityError,
    AccountCurrencyChangeBlockedError,
    AccountCurrencyMismatchError,
    NotFoundError,
)
from app.models.account import Account, AccountType
from app.models.expense_entry import ExpenseEntry
from app.models.user import User
from app.schemas.expense import ExpenseCreate, ExpenseUpdate
from app.services import account_service, expense_service

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

    @pytest.mark.asyncio
    async def test_summaries_report_has_links_from_the_sum_keys(self, monkeypatch):
        # An account is "linked" iff it appears in any source's sum (a group exists only with rows).
        linked_account = _account(id=7)
        unlinked_account = _account(id=8)
        monkeypatch.setattr(account_service.income_repository, "sum_by_account_ids", AsyncMock(return_value={}))
        monkeypatch.setattr(account_service.expense_repository, "sum_by_account_ids", AsyncMock(return_value={7: Decimal("10")}))
        monkeypatch.setattr(account_service.card_settlement_repository, "sum_by_account_ids", AsyncMock(return_value={}))

        _, linked = await account_service.get_account_summaries(AsyncMock(), [linked_account, unlinked_account], USER.id)

        assert linked == {7}


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


class TestExpenseAccountExclusivityService:
    # The schema validator only sees same-request pairs, so update_expense enforces the effective
    # rule: a credit_card expense can't keep (or gain) an account link. Otherwise the amount would be
    # debited from the account now and again at settlement — double-counting the balance.
    @pytest.mark.asyncio
    async def test_method_to_card_keeping_account_link_raises(self, monkeypatch):
        entry = ExpenseEntry(
            id=1,
            user_id=1,
            date=date(2026, 1, 1),
            amount=Decimal("10"),
            currency="ARS",
            payment_method="cash",
            credit_card_id=None,
            account_id=7,
            source="manual",
        )
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        monkeypatch.setattr(expense_service.credit_card_repository, "get_by_id", AsyncMock(return_value=object()))
        save_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "save", save_mock)

        with pytest.raises(AccountCardExclusivityError):
            await expense_service.update_expense(AsyncMock(), 1, USER, payment_method="credit_card", credit_card_id=5)

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_account_set_on_stored_card_expense_raises(self, monkeypatch):
        entry = ExpenseEntry(
            id=1,
            user_id=1,
            date=date(2026, 1, 1),
            amount=Decimal("10"),
            currency="ARS",
            payment_method="credit_card",
            credit_card_id=5,
            account_id=None,
            source="manual",
        )
        monkeypatch.setattr(expense_service.expense_repository, "get_by_id", AsyncMock(return_value=entry))
        save_mock = AsyncMock()
        monkeypatch.setattr(expense_service.expense_repository, "save", save_mock)

        with pytest.raises(AccountCardExclusivityError):
            await expense_service.update_expense(AsyncMock(), 1, USER, account_id=7)

        save_mock.assert_not_called()


class TestAccountHasLinks:
    @pytest.mark.asyncio
    async def test_true_when_expense_exists_short_circuits(self, monkeypatch):
        monkeypatch.setattr(account_service.expense_repository, "exists_by_account_id", AsyncMock(return_value=True))
        income_mock = AsyncMock(return_value=False)
        monkeypatch.setattr(account_service.income_repository, "exists_by_account_id", income_mock)
        monkeypatch.setattr(account_service.card_settlement_repository, "exists_by_account_id", AsyncMock(return_value=False))

        assert await account_service.account_has_links(AsyncMock(), 7, 1) is True
        income_mock.assert_not_awaited()  # short-circuits once the expense check is True

    @pytest.mark.asyncio
    async def test_false_when_none_exist(self, monkeypatch):
        monkeypatch.setattr(account_service.expense_repository, "exists_by_account_id", AsyncMock(return_value=False))
        monkeypatch.setattr(account_service.income_repository, "exists_by_account_id", AsyncMock(return_value=False))
        monkeypatch.setattr(account_service.card_settlement_repository, "exists_by_account_id", AsyncMock(return_value=False))

        assert await account_service.account_has_links(AsyncMock(), 7, 1) is False


class TestAccountCurrencyLock:
    # An account's currency is locked once money links to it — changing it would silently mix
    # currencies in the derived balance (mirrors the investment base-currency lock).
    @pytest.mark.asyncio
    async def test_currency_change_blocked_when_linked(self, monkeypatch):
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(account_service, "account_has_links", AsyncMock(return_value=True))
        save_mock = AsyncMock()
        monkeypatch.setattr(account_service.account_repository, "save", save_mock)

        with pytest.raises(AccountCurrencyChangeBlockedError):
            await account_service.update_account(AsyncMock(), 7, USER, currency="USD")

        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_currency_change_allowed_when_no_links(self, monkeypatch):
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(account_service, "account_has_links", AsyncMock(return_value=False))
        monkeypatch.setattr(account_service.account_repository, "save", AsyncMock())
        session = AsyncMock()

        result = await account_service.update_account(session, 7, USER, currency="USD")

        assert result.currency == "USD"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_same_currency_is_not_a_change_and_skips_the_link_check(self, monkeypatch):
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account(currency="ARS")))
        has_links = AsyncMock(return_value=True)
        monkeypatch.setattr(account_service, "account_has_links", has_links)
        monkeypatch.setattr(account_service.account_repository, "save", AsyncMock())
        session = AsyncMock()

        await account_service.update_account(session, 7, USER, currency="ARS")

        has_links.assert_not_awaited()  # equal currency short-circuits before the link check
        session.commit.assert_awaited_once()
