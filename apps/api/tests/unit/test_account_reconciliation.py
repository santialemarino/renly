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
from app.services import account_service

# Account reconciliation is the point-in-time Option-F true-up: the derived balance at a date is
# compared with the real balance the user read, and the gap becomes exactly one dated adjustment
# entry linked to the account. Persistence is mocked (AsyncMock), matching the other service tests.

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)
TODAY = date(2026, 7, 29)


# EVERY money source an account balance is made of, with the sign it carries and the repository
# attribute each is read through. The list itself is the invariant this file exists to pin: a source
# present in account_service.get_account_balances and absent from compute_account_balance_at does not
# merely under-report — it makes the reconciliation post an adjustment for money the account really did
# move. Four were missing before PR 8b, all four of them shared-money sources.
_BALANCE_SOURCES = (
    ("income_repository", "sum_by_account_ids", 1),
    ("expense_repository", "sum_by_account_ids", -1),
    ("card_settlement_repository", "sum_by_account_ids", -1),
    ("transfer_repository", "sum_in_by_account_ids", 1),
    ("transfer_repository", "sum_out_by_account_ids", -1),
    ("pot_ownership_repository", "sum_in_by_account_ids", 1),
    ("pot_ownership_repository", "sum_out_by_account_ids", -1),
    ("shared_expense_repository", "sum_by_account_ids", -1),
    ("shared_income_repository", "sum_by_account_ids", 1),
    ("group_settlement_repository", "sum_in_by_account_ids", 1),
    ("group_settlement_repository", "sum_out_by_account_ids", -1),
)


# Stubs every balance source at once, and returns the mocks keyed by (repository, method).
#
# `amounts` gives a source its own figure; anything unnamed answers zero. Stubbing them ALL from one
# list is what stops a test from silently leaving a new source unstubbed — which under an AsyncMock
# session is not an error, just a Mock arriving where a Decimal was expected.
def _stub_sums(monkeypatch, amounts: dict[tuple[str, str], Decimal] | None = None) -> dict:
    mocks: dict = {}
    for repo, method, _sign in _BALANCE_SOURCES:
        value = (amounts or {}).get((repo, method), ZERO)
        mock = AsyncMock(return_value={7: value} if value else {})
        monkeypatch.setattr(getattr(svc, repo), method, mock)
        mocks[(repo, method)] = mock
    return mocks


# One distinct figure per source, so a term the formula drops — or reads with the wrong sign — changes
# the answer. Equal values would let a dropped `+x` and a dropped `-x` cancel.
def _distinct_amounts() -> dict[tuple[str, str], Decimal]:
    return {(repo, method): Decimal(str((index + 1) * 7)) for index, (repo, method, _sign) in enumerate(_BALANCE_SOURCES)}


# What the formula must produce for _distinct_amounts, computed from the signs rather than by calling
# the formula twice.
def _expected_total(opening: Decimal) -> Decimal:
    amounts = _distinct_amounts()
    return opening + sum(sign * amounts[(repo, method)] for repo, method, sign in _BALANCE_SOURCES)


ZERO = Decimal(0)


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
    _stub_sums(
        monkeypatch,
        {
            ("income_repository", "sum_by_account_ids"): (income or {}).get(7, ZERO),
            ("expense_repository", "sum_by_account_ids"): (expenses or {}).get(7, ZERO),
            ("card_settlement_repository", "sum_by_account_ids"): (settlements or {}).get(7, ZERO),
            ("transfer_repository", "sum_in_by_account_ids"): (transfers_in or {}).get(7, ZERO),
            ("transfer_repository", "sum_out_by_account_ids"): (transfers_out or {}).get(7, ZERO),
        },
    )
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
    async def test_it_reads_the_same_sources_the_live_balance_does(self, monkeypatch):
        # TWO DERIVATIONS, ONE FACT. account_service.get_account_balances answers "what is in this
        # account now" and this answers "what was in it at a date"; the second's own comment says it
        # mirrors the first. A source in one and not the other is the failure that matters, and it is
        # invisible to every other test here because each of those stubs only the sources it names.
        #
        # Every source gets a DISTINCT figure, so a dropped `+x` cannot be cancelled by a dropped `-x`.
        _stub_sums(monkeypatch, _distinct_amounts())
        account = _account()
        dated = await svc.compute_account_balance_at(AsyncMock(), account, TODAY)
        live = await account_service.get_account_balances(AsyncMock(), [account], USER.id)
        assert dated == live[7] == _expected_total(account.opening_balance)

    @pytest.mark.asyncio
    async def test_unions_opening_income_expenses_and_settlements(self, monkeypatch):
        _stub_sums(
            monkeypatch,
            {
                ("income_repository", "sum_by_account_ids"): Decimal("500"),
                ("expense_repository", "sum_by_account_ids"): Decimal("300"),
                ("card_settlement_repository", "sum_by_account_ids"): Decimal("150"),
            },
        )

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(), date(2026, 6, 30))

        assert balance == Decimal("1050")  # 1000 + 500 - 300 - 150

    @pytest.mark.asyncio
    async def test_a_shared_expense_fronted_from_this_account_leaves_it(self, monkeypatch):
        # The money really left, whoever ends up owing whom. Missing this term made the reconciliation
        # compute a balance too HIGH by the whole bill and write the difference in as spending nobody did.
        _stub_sums(monkeypatch, {("shared_expense_repository", "sum_by_account_ids"): Decimal("400")})
        assert await svc.compute_account_balance_at(AsyncMock(), _account(), TODAY) == Decimal("600")

    @pytest.mark.asyncio
    async def test_shared_income_paid_into_this_account_arrives_in_it(self, monkeypatch):
        _stub_sums(monkeypatch, {("shared_income_repository", "sum_by_account_ids"): Decimal("250")})
        assert await svc.compute_account_balance_at(AsyncMock(), _account(), TODAY) == Decimal("1250")

    @pytest.mark.asyncio
    async def test_both_settle_up_legs_move_this_account(self, monkeypatch):
        # Two legs with DIFFERENT figures, so a formula reading one leg twice shows up as a wrong total
        # rather than as the right one.
        _stub_sums(
            monkeypatch,
            {
                ("group_settlement_repository", "sum_in_by_account_ids"): Decimal("300"),
                ("group_settlement_repository", "sum_out_by_account_ids"): Decimal("120"),
            },
        )
        assert await svc.compute_account_balance_at(AsyncMock(), _account(), TODAY) == Decimal("1180")

    @pytest.mark.asyncio
    async def test_opening_balance_excluded_before_the_account_opened(self, monkeypatch):
        _stub_sums(monkeypatch)

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(opening_date=date(2026, 5, 1)), date(2026, 4, 30))

        assert balance == Decimal(0)

    @pytest.mark.asyncio
    async def test_every_sum_is_bounded_by_the_as_of_date(self, monkeypatch):
        # ALL of them must carry the bound — a missing one would silently include rows dated after
        # as_of_date, so the recorded computed_balance would not be a point-in-time figure at all.
        mocks = _stub_sums(monkeypatch)

        await svc.compute_account_balance_at(AsyncMock(), _account(), date(2026, 6, 30))

        for key, mock in mocks.items():
            assert mock.await_args.kwargs.get("as_of_date") == date(2026, 6, 30), key

    @pytest.mark.asyncio
    async def test_opening_balance_included_on_the_opening_date_itself(self, monkeypatch):
        # The boundary: the guard is `opening_date <= as_of_date`, so the opening date counts.
        _stub_sums(monkeypatch)

        balance = await svc.compute_account_balance_at(AsyncMock(), _account(opening_date=date(2026, 5, 1)), date(2026, 5, 1))

        assert balance == Decimal("1000")

    @pytest.mark.asyncio
    async def test_balance_can_be_negative(self, monkeypatch):
        _stub_sums(monkeypatch, {("expense_repository", "sum_by_account_ids"): Decimal("2500")})

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
