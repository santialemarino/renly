from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app.domain import (
    AccountCardExclusivityError,
    AccountCurrencyChangeBlockedByDefaultError,
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
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await account_service.validate_account_link(AsyncMock(), USER, 7, "ARS")

    @pytest.mark.asyncio
    async def test_currency_mismatch_raises(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(currency="ARS")))
        with pytest.raises(AccountCurrencyMismatchError):
            await account_service.validate_account_link(AsyncMock(), USER, 7, "USD")

    @pytest.mark.asyncio
    async def test_matching_currency_ok(self, monkeypatch):
        monkeypatch.setattr(account_service.account_repository, "get_by_id", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(account_service.account_repository, "get_by_id_any_scope", AsyncMock(return_value=_account(currency="ARS")))
        await account_service.validate_account_link(AsyncMock(), USER, 7, "ARS")


# Every source the balance union reads, as (module attribute, method, keyword). Eleven of them now, so
# the tests below name only the ones they care about and the rest stub to nothing — a test that had to
# restate all eleven would drift the moment a twelfth arrived, which is exactly what happened when the
# flow half added three and then a fourth.
_BALANCE_SOURCES = (
    ("income_repository", "sum_by_account_ids", "income"),
    ("expense_repository", "sum_by_account_ids", "expenses"),
    ("card_settlement_repository", "sum_by_account_ids", "card_settlements"),
    ("transfer_repository", "sum_in_by_account_ids", "transfers_in"),
    ("transfer_repository", "sum_out_by_account_ids", "transfers_out"),
    ("pot_ownership_repository", "sum_in_by_account_ids", "ownership_in"),
    ("pot_ownership_repository", "sum_out_by_account_ids", "ownership_out"),
    ("shared_expense_repository", "sum_by_account_ids", "shared_expenses"),
    ("shared_income_repository", "sum_by_account_ids", "shared_income"),
    ("group_settlement_repository", "sum_in_by_account_ids", "group_settlements_in"),
    ("group_settlement_repository", "sum_out_by_account_ids", "group_settlements_out"),
)

# The sources feeding the currency lock. Not the same list: `linked` runs its own UNBOUNDED queries,
# and a transfer or a group settlement counts on either leg.
_LINKED_SOURCES = (
    ("income_repository", "income"),
    ("expense_repository", "expenses"),
    ("card_settlement_repository", "card_settlements"),
    ("transfer_repository", "transfers"),
    ("shared_expense_repository", "shared_expenses"),
    ("shared_income_repository", "shared_income"),
    ("group_settlement_repository", "group_settlements"),
)


def _stub_sums(monkeypatch, **totals: dict) -> None:
    for attribute, method, keyword in _BALANCE_SOURCES:
        monkeypatch.setattr(getattr(account_service, attribute), method, AsyncMock(return_value=totals.get(keyword, {})))


def _stub_linked(monkeypatch, **linked: set) -> None:
    for attribute, keyword in _LINKED_SOURCES:
        monkeypatch.setattr(getattr(account_service, attribute), "linked_account_ids", AsyncMock(return_value=linked.get(keyword, set())))


class TestBalanceUnion:
    @pytest.mark.asyncio
    async def test_every_term_of_the_union_is_applied_with_the_right_sign(self, monkeypatch):
        # One distinct figure per term, so a dropped term or a flipped sign changes the total by an
        # amount no other term could produce. Equal values would let two errors cancel.
        account = _account(id=7, opening_balance=Decimal("1000"))
        _stub_sums(
            monkeypatch,
            income={7: Decimal("500")},
            expenses={7: Decimal("200")},
            card_settlements={7: Decimal("50")},
            transfers_in={7: Decimal("11")},
            transfers_out={7: Decimal("13")},
            ownership_in={7: Decimal("17")},
            ownership_out={7: Decimal("19")},
            shared_expenses={7: Decimal("23")},
            group_settlements_in={7: Decimal("29")},
            group_settlements_out={7: Decimal("31")},
        )
        _stub_linked(monkeypatch)

        balances = await account_service.get_account_balances(AsyncMock(), [account], USER.id)

        # 1000 + 500 − 200 − 50 + 11 − 13 + 17 − 19 − 23 + 29 − 31 = 1221.
        assert balances == {7: Decimal("1221")}

    @pytest.mark.asyncio
    async def test_no_linked_rows_is_opening_balance(self, monkeypatch):
        account = _account(id=7, opening_balance=Decimal("1000"))
        _stub_sums(monkeypatch)
        _stub_linked(monkeypatch)

        balances = await account_service.get_account_balances(AsyncMock(), [account], USER.id)

        assert balances == {7: Decimal("1000")}

    @pytest.mark.asyncio
    async def test_empty_accounts_short_circuits(self):
        # No repo calls when there are no accounts.
        assert await account_service.get_account_balances(AsyncMock(), [], USER.id) == {}

    @pytest.mark.asyncio
    async def test_linked_is_unbounded_not_derived_from_the_balance_sums(self, monkeypatch):
        """The currency lock is about denomination, not about reaching the balance.

        The sums are bounded below by opening_date, so an account whose only rows PREDATE its opening
        contributes nothing to them — deriving `linked` from the sum keys would report it unlocked and
        the UI would offer a currency change the API then refuses. `linked` therefore runs its own
        unbounded queries: account 7 here has an expense that no sum sees, and is still linked.
        """
        _stub_sums(monkeypatch)
        _stub_linked(monkeypatch, expenses={7})

        _, linked = await account_service.get_account_summaries(AsyncMock(), [_account(id=7), _account(id=8)], USER.id)

        assert linked == {7}

    @pytest.mark.asyncio
    async def test_a_transfer_alone_locks_the_currency(self, monkeypatch):
        # An account that has only ever sent or received money must still be currency-locked.
        _stub_sums(monkeypatch)
        _stub_linked(monkeypatch, transfers={7})

        _, linked = await account_service.get_account_summaries(AsyncMock(), [_account(id=7)], USER.id)

        assert linked == {7}

    @pytest.mark.asyncio
    async def test_a_shared_expense_alone_locks_the_currency(self, monkeypatch):
        # A group spending from this account denominates it just as firmly as its owner does. Without
        # this the owner could re-denominate an account the group's expenses are recorded against, and
        # every one of those figures would silently change what it means.
        _stub_sums(monkeypatch)
        _stub_linked(monkeypatch, shared_expenses={7})

        _, linked = await account_service.get_account_summaries(AsyncMock(), [_account(id=7)], USER.id)

        assert linked == {7}

    @pytest.mark.asyncio
    async def test_a_group_settlement_alone_locks_the_currency(self, monkeypatch):
        _stub_sums(monkeypatch)
        _stub_linked(monkeypatch, group_settlements={7})

        _, linked = await account_service.get_account_summaries(AsyncMock(), [_account(id=7)], USER.id)

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
        monkeypatch.setattr(account_service.transfer_repository, "exists_by_account_id", AsyncMock(return_value=False))

        assert await account_service.account_has_links(AsyncMock(), 7, 1) is True
        income_mock.assert_not_awaited()  # short-circuits once the expense check is True

    @pytest.mark.asyncio
    async def test_false_when_none_exist(self, monkeypatch):
        for repo in ("expense_repository", "income_repository", "card_settlement_repository", "transfer_repository"):
            monkeypatch.setattr(getattr(account_service, repo), "exists_by_account_id", AsyncMock(return_value=False))
        # The three group sources answer with the account-id SET they touch rather than a bool, because
        # their queries carry no user filter and take a list — the same functions the currency lock reads.
        _stub_linked(monkeypatch)

        assert await account_service.account_has_links(AsyncMock(), 7, 1) is False

    @pytest.mark.parametrize("source", ["shared_expenses", "shared_income", "group_settlements"])
    @pytest.mark.asyncio
    async def test_true_when_only_a_GROUP_has_used_it(self, monkeypatch, source):
        # An account whose only money movement belongs to a group is still linked, whichever of the
        # three ways it got there. Without any one of them the owner could re-denominate the account
        # while the group's figures still referred to the old currency, or move its opening_date past
        # rows the balance is bounded below by — and this is the check the UPDATE actually consults.
        for repo in ("expense_repository", "income_repository", "card_settlement_repository", "transfer_repository"):
            monkeypatch.setattr(getattr(account_service, repo), "exists_by_account_id", AsyncMock(return_value=False))
        _stub_linked(monkeypatch, **{source: {7}})

        assert await account_service.account_has_links(AsyncMock(), 7, 1) is True


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
        monkeypatch.setattr(account_service, "count_default_references", AsyncMock(return_value=0))
        monkeypatch.setattr(account_service.account_repository, "save", AsyncMock())
        session = AsyncMock()

        result = await account_service.update_account(session, 7, USER, currency="USD")

        assert result.currency == "USD"
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_currency_change_blocked_by_a_standing_default(self, monkeypatch):
        # No money has moved, so account_has_links is False and the "linked entries" error would be a
        # lie — but a card or plan still points here, and the moment the currencies diverge every
        # charge it was meant to attribute stops being attributed, silently.
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account(currency="ARS")))
        monkeypatch.setattr(account_service, "account_has_links", AsyncMock(return_value=False))
        monkeypatch.setattr(account_service, "count_default_references", AsyncMock(return_value=2))
        save_mock = AsyncMock()
        monkeypatch.setattr(account_service.account_repository, "save", save_mock)

        with pytest.raises(AccountCurrencyChangeBlockedByDefaultError) as exc:
            await account_service.update_account(AsyncMock(), 7, USER, currency="USD")

        assert exc.value.extra == {"referencing_count": 2}
        save_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_opening_date_change_is_not_blocked_by_a_standing_default(self, monkeypatch):
        # A default has no bearing on the opening anchor — only on which currency it must match.
        monkeypatch.setattr(account_service, "get_account", AsyncMock(return_value=_account()))
        monkeypatch.setattr(account_service, "account_has_links", AsyncMock(return_value=False))
        counter = AsyncMock(return_value=3)
        monkeypatch.setattr(account_service, "count_default_references", counter)
        monkeypatch.setattr(account_service.account_repository, "save", AsyncMock())

        await account_service.update_account(AsyncMock(), 7, USER, opening_date=date(2026, 2, 1))

        counter.assert_not_awaited()

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
