from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import (
    AccountReconciliationBeforeLastError,
    AccountReconciliationBeforeOpeningError,
    AccountReconciliationFutureDateError,
    AccountReconciliationNotLatestError,
    AccountReconciliationPotNotDividedError,
    NotFoundError,
)
from app.models.account import Account, AccountType
from app.models.account_reconciliation import AccountReconciliation
from app.models.expense_entry import ExpenseCategory
from app.models.group import Group, GroupKind, GroupMember
from app.models.income_entry import IncomeCategory
from app.models.notification import NotificationEvent
from app.models.pot import Pot
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.shared_income import IncomeDestination
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


# The four repositories whose sums take a user id, because their tables keep `user_id NOT NULL` and
# carry no pot_id at all (§3 — a shared flow lives in its own table). The other seven are scope-free or
# resolve scope from the JOINED account, which is what makes a pot's account report the same balance to
# every member who can see it.
_OWNER_SCOPED_REPOS = frozenset({"income_repository", "expense_repository", "card_settlement_repository", "transfer_repository"})


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
    monkeypatch.setattr(svc.account_service, "get_account_in_scope", AsyncMock(return_value=account))
    monkeypatch.setattr(svc.account_repository, "lock", AsyncMock())
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
    async def test_every_sum_is_scoped_by_the_ACCOUNTS_owner_not_the_callers(self, monkeypatch):
        # What makes this function correct for a POT's account without a scope branch, stated as an
        # assertion because it reads like an omission. Each user-scoped sum is bounded by
        # `account.user_id` — NULL on a pot's account — and the four tables those read keep user_id
        # NOT NULL, so they contribute nothing, which is the true answer: ensure_private_funding refuses
        # a private entry funded from a co-owned account and a transfer may not cross a scope boundary.
        # Every source that CAN reach a pot's account is scope-free or reads account_scope_matches.
        #
        # Asserted on the ARGUMENT, because the sums are stubbed and answer the same figure whatever
        # they are asked. Threading the CALLER's id instead would pass every other test in this file.
        mocks = _stub_sums(monkeypatch)
        await svc.compute_account_balance_at(AsyncMock(), _account(user_id=None, pot_id=4), TODAY)

        scoped = {(repo, method) for repo, method, _ in _BALANCE_SOURCES if repo in _OWNER_SCOPED_REPOS}
        for key in scoped:
            assert mocks[key].await_args.args[2] is None, key
        for key in set(mocks) - scoped:
            assert len(mocks[key].await_args.args) == 2, key

    @pytest.mark.asyncio
    async def test_a_private_accounts_sums_carry_its_owner(self, monkeypatch):
        # The other side of the same argument, so a mutation hardcoding None passes nothing.
        mocks = _stub_sums(monkeypatch)
        await svc.compute_account_balance_at(AsyncMock(), _account(), TODAY)

        for repo, method, _ in _BALANCE_SOURCES:
            if repo in _OWNER_SCOPED_REPOS:
                assert mocks[(repo, method)].await_args.args[2] == 1, (repo, method)

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
        monkeypatch.setattr(svc.account_service, "get_account_in_scope", AsyncMock(side_effect=NotFoundError("Account not found.")))
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
        monkeypatch.setattr(svc.account_service, "get_account_in_scope", AsyncMock(side_effect=NotFoundError("Account not found.")))
        with pytest.raises(NotFoundError):
            await svc.list_reconciliations(AsyncMock(), 7, USER)

    @pytest.mark.asyncio
    async def test_get_raises_when_the_reconciliation_is_missing(self, monkeypatch):
        monkeypatch.setattr(svc.account_service, "get_account_in_scope", AsyncMock(return_value=_account()))
        monkeypatch.setattr(svc.account_reconciliation_repository, "get_by_id", AsyncMock(return_value=None))
        with pytest.raises(NotFoundError):
            await svc.get_reconciliation(AsyncMock(), 7, 42, USER)

    @pytest.mark.asyncio
    async def test_delete_commits_once(self, monkeypatch):
        # get_reconciliation is deliberately NOT stubbed, so the real ownership chain runs:
        # account_service.get_account_in_scope (either scope) then get_by_id scoped to the account.
        row = _reconciliation(as_of_date=date(2026, 7, 20))
        monkeypatch.setattr(svc.account_service, "get_account_in_scope", AsyncMock(return_value=_account()))
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
        monkeypatch.setattr(svc.account_service, "get_account_in_scope", AsyncMock(return_value=_account()))
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


# --- A POT's account (PR 14) ---
#
# Everything below is about the ONE thing that differs by scope: where the adjustment lands. A private
# adjustment is an expense_entries / income_entries row owned by one user, and a shared one cannot be —
# those tables keep user_id NOT NULL and carry no pot_id, and the pot account's balance sums filter on
# that same column, so such a row would leave the drift open. (What stops one existing is
# `ensure_private_funding` in the service, not any constraint; tests/integration constructs the row it
# refuses and watches the two balance derivations diverge.) The shared adjustment is a shared_expenses /
# shared_income row split across the pot's owners.

POT = Pot(id=4, group_id=2, name="Depto", base_currency="ARS", created_by=USER.id)
GROUP = Group(id=2, name="Casa", kind=GroupKind.household, created_by=USER.id)
SEAT = GroupMember(id=100, group_id=2, user_id=USER.id, display_name="Santi")
# 60/40, deliberately uneven: an equal split would be indistinguishable from an ownership one.
OWNER_SHARES = {100: Decimal("120.00"), 101: Decimal("80.00")}


def _shared_account(**overrides) -> Account:
    return _account(user_id=None, pot_id=4, **overrides)


# Wires create_reconciliation for a POT's account: the scope resolution, the ownership split, and
# capture-and-assign-id fakes for the shared rows the service writes.
#
# `shares` is what owner_shares answers. Passing {} is the UNDIVIDED pot — the one refusal this flow
# has — rather than a separate flag, because that is exactly how the service learns of it.
def _wire_shared(monkeypatch, account: Account, *, shares=None, today: date = TODAY, last_reconciled: date | None = None) -> dict:
    captured = _wire(monkeypatch, account, today=today, last_reconciled=last_reconciled)
    monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, None)))
    monkeypatch.setattr(svc.pot_repository, "lock", AsyncMock())
    monkeypatch.setattr(svc.group_repository, "get_by_id", AsyncMock(return_value=GROUP))
    monkeypatch.setattr(
        svc.pot_ownership_service,
        "owner_shares",
        AsyncMock(return_value=OWNER_SHARES if shares is None else shares),
    )
    monkeypatch.setattr(svc.pot_service, "list_notifiable_user_ids", AsyncMock(return_value=[2]))
    captured["audit"] = AsyncMock()
    captured["dispatch"] = AsyncMock()
    monkeypatch.setattr(svc.shared_audit_service, "record", captured["audit"])
    monkeypatch.setattr(svc.notification_service, "dispatch", captured["dispatch"])

    async def fake_create_shared_income(_session, row):
        row.id = 71
        captured["shared_income"] = row
        return row

    async def fake_create_shared_expense(_session, row):
        row.id = 72
        captured["shared_expense"] = row
        return row

    async def fake_income_splits(_session, splits):
        captured["income_splits"] = splits
        return splits

    async def fake_expense_splits(_session, splits):
        captured["expense_splits"] = splits
        return splits

    monkeypatch.setattr(svc.shared_income_repository, "create", fake_create_shared_income)
    monkeypatch.setattr(svc.shared_expense_repository, "create", fake_create_shared_expense)
    monkeypatch.setattr(svc.shared_income_repository, "create_splits", fake_income_splits)
    monkeypatch.setattr(svc.shared_expense_repository, "create_splits", fake_expense_splits)
    return captured


class TestSharedAccountScope:
    @pytest.mark.asyncio
    async def test_the_row_belongs_to_the_pot_and_names_who_ran_it(self, monkeypatch):
        # user_id and pot_id are mutually exclusive by CHECK, and which one is set decides every
        # downstream read: a pot's reconciliation is countable by each co-owner, a private one is not.
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        row = captured["reconciliation"]
        assert (row.user_id, row.pot_id, row.created_by) == (None, 4, USER.id)

    @pytest.mark.asyncio
    async def test_a_private_account_still_belongs_to_its_owner(self, monkeypatch):
        # The other side of the same branch, so a mutation flipping the condition fails here too.
        captured = _wire(monkeypatch, _account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        row = captured["reconciliation"]
        assert (row.user_id, row.pot_id, row.created_by) == (USER.id, None, USER.id)

    @pytest.mark.asyncio
    async def test_a_shortfall_posts_a_shared_expense_drawn_from_the_account(self, monkeypatch):
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        expense = captured["shared_expense"]
        assert expense.group_id == 2
        assert expense.amount == Decimal("200")
        assert expense.currency == "ARS"
        assert expense.category == ExpenseCategory.account_adjustment
        assert expense.paid_from_account_id == 7
        assert expense.account_reconciliation_id == 42
        assert captured["reconciliation"].adjustment_shared_expense_id == 72
        # And nothing landed in the PRIVATE tables, which is the failure this whole branch exists to
        # avoid: such a row is invisible to the pot account's balance sums, so the drift would persist.
        assert "expense" not in captured

    @pytest.mark.asyncio
    async def test_a_surplus_posts_shared_income_into_the_account_as_joint(self, monkeypatch):
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("1200"))

        income = captured["shared_income"]
        assert income.amount == Decimal("200")
        assert income.category == IncomeCategory.account_adjustment
        assert income.paid_to_account_id == 7
        assert income.account_reconciliation_id == 42
        # Joint, because the money is sitting in a pot's account. Distributed would claim it reached
        # somebody's hands, and nothing here reached anybody.
        assert income.destination == IncomeDestination.joint
        assert captured["reconciliation"].adjustment_shared_income_id == 71
        assert "income" not in captured

    @pytest.mark.asyncio
    async def test_both_sides_of_every_split_carry_the_same_figure(self, monkeypatch):
        # THE identity the whole design rests on. A split row's two columns are what a member consumed
        # and what they fronted, and their balance is the difference — so writing the same figure twice
        # moves nobody's balance at all. The drift is money the pot already held: correcting it changes
        # what each owner HOLDS, through the NAV, and creates no debt between them.
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        splits = captured["expense_splits"]
        assert [(s.member_id, s.amount, s.paid_amount) for s in splits] == [
            (100, Decimal("120.00"), Decimal("120.00")),
            (101, Decimal("80.00"), Decimal("80.00")),
        ]
        assert sum(s.amount for s in splits) == Decimal("200")

    @pytest.mark.asyncio
    async def test_the_income_splits_carry_it_on_both_sides_too(self, monkeypatch):
        # The income side's columns are named differently (entitled / received) and the rule is the
        # same, so asserting only the expense side would leave half the identity untested.
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("1200"))

        splits = captured["income_splits"]
        assert [(s.member_id, s.amount, s.received_amount) for s in splits] == [
            (100, Decimal("120.00"), Decimal("120.00")),
            (101, Decimal("80.00"), Decimal("80.00")),
        ]

    @pytest.mark.asyncio
    async def test_the_split_is_priced_at_the_reconciled_date_and_the_difference(self, monkeypatch):
        # owner_shares is asked for the DIFFERENCE as of the RECONCILED date, not today's and not the
        # statement balance. Asserted on the arguments because the answer is stubbed: a call made with
        # the wrong total or the wrong date returns the same fixture and looks identical otherwise.
        captured = _wire_shared(monkeypatch, _shared_account())
        earlier = date(2026, 7, 20)

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=earlier, statement_balance=Decimal("800"))

        assert svc.pot_ownership_service.owner_shares.await_args.kwargs == {"total": Decimal("200"), "date": earlier}
        assert captured["shared_expense"].date == earlier

    @pytest.mark.asyncio
    async def test_a_matching_balance_writes_no_adjustment_at_all(self, monkeypatch):
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("1000"))

        assert "shared_expense" not in captured and "shared_income" not in captured
        assert captured["reconciliation"].difference == ZERO


class TestSharedAccountRefusal:
    @pytest.mark.asyncio
    async def test_an_undivided_pot_is_refused(self, monkeypatch):
        # The adjustment divides between owners, and an undivided pot has none on record — so there is
        # nobody to bear the difference. Inventing one would assert an ownership nobody agreed.
        captured = _wire_shared(monkeypatch, _shared_account(), shares={})

        with pytest.raises(AccountReconciliationPotNotDividedError):
            await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        # Refused BEFORE the reconciliation row is written, so a rejected request leaves nothing behind.
        assert "reconciliation" not in captured

    @pytest.mark.asyncio
    async def test_a_pot_divided_only_after_the_date_is_refused(self, monkeypatch):
        # The date-bounded half of the same rule, and the half the accounts list cannot express: a pot
        # divided last week cannot bear a correction dated a month ago, and only the request knows the
        # date. owner_shares is asked as of that date, so an empty answer IS the refusal.
        captured = _wire_shared(monkeypatch, _shared_account(), shares={})

        with pytest.raises(AccountReconciliationPotNotDividedError):
            await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=date(2026, 7, 1), statement_balance=Decimal("800"))

        assert svc.pot_ownership_service.owner_shares.await_args.kwargs["date"] == date(2026, 7, 1)
        assert "reconciliation" not in captured

    def test_the_refusal_rule_answers_both_ways(self):
        # ONE function, used by the accounts list and raised by the write. Both directions, because a
        # rule that only ever says no is indistinguishable from a rule that always says no.
        assert svc.reconciliation_refusal(None, set()) is None
        assert svc.reconciliation_refusal(4, {4}) is None
        assert isinstance(svc.reconciliation_refusal(4, set()), AccountReconciliationPotNotDividedError)
        # A pot id that is not the one divided: the membership test is the point, not truthiness.
        assert isinstance(svc.reconciliation_refusal(4, {5}), AccountReconciliationPotNotDividedError)


class TestSharedAccountLocking:
    @pytest.mark.asyncio
    async def test_a_pot_account_locks_the_POT_and_never_the_account_row(self, monkeypatch):
        # WHICH row is locked differs by scope and is not stylistic. A locking read is governed by the
        # UPDATE policy, and accounts_scope_write requires pot WRITE access — which reconciling does not
        # — so locking the account of a pot would match no row for a read-only co-owner and take no lock
        # at all, silently. pots_scope_write's USING admits a read-only seat on purpose.
        _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        svc.pot_repository.lock.assert_awaited_once()
        assert svc.pot_repository.lock.await_args.args[1] == 4
        svc.account_repository.lock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_private_account_locks_the_account_row(self, monkeypatch):
        # The other side, so a mutation that always locks the pot fails here.
        _wire(monkeypatch, _account())
        monkeypatch.setattr(svc.pot_repository, "lock", AsyncMock())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        svc.account_repository.lock.assert_awaited_once()
        assert svc.account_repository.lock.await_args.args[1] == 7
        svc.pot_repository.lock.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_lock_is_taken_before_the_balance_is_read(self, monkeypatch):
        # The window this closes is read-then-act: two concurrent runs each see the pre-adjustment
        # balance, each compute the same difference and each post it, so the account overshoots by the
        # whole drift — and neither ordering guard notices, because both rows carry the same date.
        order: list[str] = []
        _wire_shared(monkeypatch, _shared_account())
        lock = svc.pot_repository.lock
        monkeypatch.setattr(svc.pot_repository, "lock", AsyncMock(side_effect=lambda *a: order.append("lock")))
        original = svc.compute_account_balance_at

        async def traced(*args, **kwargs):
            order.append("balance")
            return await original(*args, **kwargs)

        monkeypatch.setattr(svc, "compute_account_balance_at", traced)
        assert lock is not None

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        assert order == ["lock", "balance"]


class TestSharedAccountAnnouncement:
    @pytest.mark.asyncio
    async def test_it_audits_the_reconciliation_and_notifies_the_pot(self, monkeypatch):
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        audit = captured["audit"].await_args.kwargs
        assert audit["entity_type"] == AuditEntityType.account_reconciliation
        assert audit["action"] == AuditAction.created
        # The ACCOUNT's id, not the reconciliation's: a deletion entry has to stay meaningful once the
        # row it describes is gone. And pot_id, which is what the policy reads to decide who may see it
        # — an entry that omits it is visible to the whole group, pot policy or not.
        assert (audit["entity_id"], audit["pot_id"], audit["group_id"]) == (7, 4, 2)
        assert audit["payload"] == {"account": "Caja de ahorro $", "variant": "shortfall", "amount": "200", "currency": "ARS"}

        event, recipients, payload = captured["dispatch"].await_args.args
        assert event == NotificationEvent.pot_movement
        assert recipients == [2]
        assert payload["variant"] == "reconciliation_shortfall"
        assert (payload["pot_id"], payload["group_id"], payload["account"]) == (4, 2, "Caja de ahorro $")
        # The actor is named as the GROUP names them, never users.name — which the group may have
        # overridden and a placeholder seat never had.
        assert payload["actor"] == "Santi"

    @pytest.mark.asyncio
    async def test_the_audience_excludes_whoever_ran_it(self, monkeypatch):
        # Asserted on the ARGUMENT, because the audience read is stubbed and hands back the same
        # recipients whatever it is asked — PR 13's lesson, which a mutation sweep found by deleting it.
        _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        assert svc.pot_service.list_notifiable_user_ids.await_args.kwargs == {"exclude_user_id": USER.id}

    @pytest.mark.asyncio
    async def test_a_surplus_announces_the_other_direction(self, monkeypatch):
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("1200"))

        assert captured["audit"].await_args.kwargs["payload"]["variant"] == "surplus"
        assert captured["dispatch"].await_args.args[2]["variant"] == "reconciliation_surplus"

    @pytest.mark.asyncio
    async def test_a_zero_difference_is_audited_but_not_notified(self, monkeypatch):
        # "The account was checked and it matched" is a fact about joint money worth keeping, and it is
        # the ONLY trace such a run leaves — no adjustment row exists to stand for it. But nobody's
        # share moved, and what justifies notifying at all is that a silent adjustment moves what every
        # co-owner holds.
        captured = _wire_shared(monkeypatch, _shared_account())

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("1000"))

        assert captured["audit"].await_args.kwargs["payload"]["variant"] == "matched"
        captured["dispatch"].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_private_reconciliation_announces_nothing(self, monkeypatch):
        # Zero added friction for a solo user, which is every public user at launch.
        _wire(monkeypatch, _account())
        audit = AsyncMock()
        dispatch = AsyncMock()
        monkeypatch.setattr(svc.shared_audit_service, "record", audit)
        monkeypatch.setattr(svc.notification_service, "dispatch", dispatch)

        await svc.create_reconciliation(AsyncMock(), 7, USER, as_of_date=TODAY, statement_balance=Decimal("800"))

        audit.assert_not_awaited()
        dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_deleting_a_shared_reconciliation_announces_the_removal(self, monkeypatch):
        # Deleting restores the balance, which moves every share back — the same reason recording it
        # announces in the first place.
        captured = _wire_shared(monkeypatch, _shared_account())
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_by_id",
            AsyncMock(return_value=_reconciliation(user_id=None, pot_id=4, as_of_date=TODAY)),
        )
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_latest_dates_by_account_ids",
            AsyncMock(return_value={7: TODAY}),
        )
        monkeypatch.setattr(svc.account_reconciliation_repository, "delete", AsyncMock())

        await svc.delete_reconciliation(AsyncMock(), 7, 42, USER)

        assert captured["audit"].await_args.kwargs["action"] == AuditAction.deleted
        assert captured["dispatch"].await_args.args[2]["variant"] == "reconciliation_removed"

    @pytest.mark.asyncio
    async def test_deleting_a_matched_reconciliation_notifies_nobody(self, monkeypatch):
        # Symmetric with recording one: nothing moved back, because nothing had moved.
        captured = _wire_shared(monkeypatch, _shared_account())
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_by_id",
            AsyncMock(return_value=_reconciliation(user_id=None, pot_id=4, as_of_date=TODAY, difference=ZERO)),
        )
        monkeypatch.setattr(
            svc.account_reconciliation_repository,
            "get_latest_dates_by_account_ids",
            AsyncMock(return_value={7: TODAY}),
        )
        monkeypatch.setattr(svc.account_reconciliation_repository, "delete", AsyncMock())

        await svc.delete_reconciliation(AsyncMock(), 7, 42, USER)

        assert captured["audit"].await_args.kwargs["action"] == AuditAction.deleted
        captured["dispatch"].assert_not_awaited()


class TestDifferenceBearers:
    @pytest.mark.asyncio
    async def test_a_private_account_names_nobody(self, monkeypatch):
        # And costs no query: a private account's difference is one person's, so there is nothing to
        # disclose and no roster to read.
        require_visible = AsyncMock()
        monkeypatch.setattr(svc.pot_service, "require_visible", require_visible)

        assert await svc.list_difference_bearers(AsyncMock(), _account(), USER, as_of_date=TODAY) == []
        require_visible.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_it_names_each_owner_with_their_percentage_largest_first(self, monkeypatch):
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, None)))
        monkeypatch.setattr(
            svc.pot_ownership_service,
            "owner_shares",
            AsyncMock(return_value={101: Decimal("40.00"), 100: Decimal("60.00")}),
        )
        monkeypatch.setattr(
            svc.group_repository,
            "list_members",
            AsyncMock(return_value=[SEAT, GroupMember(id=101, group_id=2, user_id=2, display_name="Ana")]),
        )

        bearers = await svc.list_difference_bearers(AsyncMock(), _shared_account(), USER, as_of_date=TODAY)

        # Largest first, and the fixture arrives in the OPPOSITE order so the sort is what produces it.
        assert [(b.display_name, b.percentage) for b in bearers] == [("Santi", Decimal("60.00")), ("Ana", Decimal("40.00"))]

    @pytest.mark.asyncio
    async def test_it_asks_for_a_total_of_one_hundred(self, monkeypatch):
        # A PERCENTAGE, not an amount: the difference is not known until the user types a statement
        # balance, and multiplying in the browser would drift from the row that gets written, whose
        # rounding remainder goes to the largest holder.
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, None)))
        monkeypatch.setattr(svc.pot_ownership_service, "owner_shares", AsyncMock(return_value={100: Decimal("100.00")}))
        monkeypatch.setattr(svc.group_repository, "list_members", AsyncMock(return_value=[SEAT]))

        await svc.list_difference_bearers(AsyncMock(), _shared_account(), USER, as_of_date=TODAY)

        assert svc.pot_ownership_service.owner_shares.await_args.kwargs["total"] == Decimal("100")

    @pytest.mark.asyncio
    async def test_an_undivided_pot_names_nobody_rather_than_refusing(self, monkeypatch):
        # This is a PREVIEW, not the write. The row already says can_reconcile is false, and raising
        # here would turn a dialog's live re-read into an error the user cannot act on.
        monkeypatch.setattr(svc.pot_service, "require_visible", AsyncMock(return_value=(POT, SEAT, None)))
        monkeypatch.setattr(svc.pot_ownership_service, "owner_shares", AsyncMock(return_value={}))

        assert await svc.list_difference_bearers(AsyncMock(), _shared_account(), USER, as_of_date=TODAY) == []
