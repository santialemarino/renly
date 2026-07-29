from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseCategory
from app.models.user import User
from app.services import card_reconciliation_service
from app.services.card_reconciliation_service import compute_reconciliation_difference, cumulative_balances_at

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


# Wires create_or_replace's dependencies: an owned card, a fixed computed balance, and a
# capture-and-assign-id fake for the adjustment row the service writes.
def _wire_create(monkeypatch, *, computed):
    captured: dict = {}
    card = CreditCard(id=7, user_id=1, name="Visa", closing_day=20, due_day=28, currency="ARS")
    monkeypatch.setattr(card_reconciliation_service, "_get_card_or_404", AsyncMock(return_value=card))
    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "get_by_period", AsyncMock(return_value=None))
    monkeypatch.setattr(card_reconciliation_service, "compute_bucket_balance_at", AsyncMock(return_value=computed))
    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "save", AsyncMock())

    async def fake_create_reconciliation(_session, reconciliation):
        reconciliation.id = 42
        captured["reconciliation"] = reconciliation
        return reconciliation

    async def fake_create_expense(_session, entry):
        entry.id = 91
        captured["expense"] = entry
        return entry

    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "create", fake_create_reconciliation)
    monkeypatch.setattr(card_reconciliation_service.expense_repository, "create", fake_create_expense)
    return captured


# --- compute_reconciliation_difference ---


class TestComputeReconciliationDifference:
    def test_positive_difference_creates_expense_side(self):
        # Bank says 1100, app computed 1000 -> 100 unaccounted (fees / taxes).
        assert compute_reconciliation_difference(Decimal("1100"), Decimal("1000")) == Decimal("100")

    def test_negative_difference_creates_income_side(self):
        # Bank says 900, app computed 1000 -> -100 (credit / refund the app missed).
        assert compute_reconciliation_difference(Decimal("900"), Decimal("1000")) == Decimal("-100")

    def test_zero_difference_means_no_adjustment(self):
        assert compute_reconciliation_difference(Decimal("1000"), Decimal("1000")) == Decimal("0")

    def test_two_decimal_precision_preserved(self):
        # Bank: 1234.56, computed: 1200.00 -> 34.56.
        assert compute_reconciliation_difference(Decimal("1234.56"), Decimal("1200.00")) == Decimal("34.56")

    def test_large_amount(self):
        assert compute_reconciliation_difference(Decimal("9999999.99"), Decimal("9999999.00")) == Decimal("0.99")

    def test_negative_computed_balance(self):
        # Overpaid bucket — computed_balance is negative (credit balance on card).
        # Bank says 0 (cleared the credit), app says -50 -> difference 50 (the credit was somehow consumed).
        assert compute_reconciliation_difference(Decimal("0"), Decimal("-50")) == Decimal("50")


# --- cumulative_balances_at (batched running-balance walk, P08 perf) ---


class TestCumulativeBalancesAt:
    def test_running_balance_across_closings_with_settlements(self):
        # Activity before the earliest closing feeds its base; a closing with no new expense
        # carries the running total; settlements net against expenses.
        expense_daily = [
            (date(2025, 12, 5), Decimal("20")),
            (date(2026, 1, 10), Decimal("100")),
            (date(2026, 2, 5), Decimal("50")),
            (date(2026, 3, 20), Decimal("30")),
        ]
        settlement_daily = [
            (date(2026, 2, 15), Decimal("40")),
            (date(2026, 4, 1), Decimal("10")),
        ]
        closings = [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30)]

        result = cumulative_balances_at(closings, expense_daily, settlement_daily)

        assert result == {
            date(2026, 1, 31): Decimal("120"),  # 20 + 100
            date(2026, 2, 28): Decimal("130"),  # +50 - 40
            date(2026, 3, 31): Decimal("160"),  # +30, no settlement <= 3/31
            date(2026, 4, 30): Decimal("150"),  # -10 settlement, no new expense
        }

    def test_no_activity_yields_zero_at_every_closing(self):
        closings = [date(2026, 1, 31), date(2026, 2, 28)]
        result = cumulative_balances_at(closings, [], [])
        assert result == {date(2026, 1, 31): Decimal("0"), date(2026, 2, 28): Decimal("0")}


# --- list_recent_statements: user-timezone "today" ---


# Patches the user-today derivation and every repository read list_recent_statements makes, so the
# statement walk runs purely in memory (no session — passed as None). get_user_today is patched on
# the imported settings_service module (the service calls it as settings_service.get_user_today).
def _patch_statement_deps(monkeypatch, user_today):
    monkeypatch.setattr(card_reconciliation_service.settings_service, "get_user_today", AsyncMock(return_value=user_today))
    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "list_by_card", AsyncMock(return_value=[]))
    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "get_first_activity_date", AsyncMock(return_value=None))
    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "list_expense_daily_sums", AsyncMock(return_value=[]))
    monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "list_settlement_daily_sums", AsyncMock(return_value=[]))


class TestListRecentStatementsUserToday:
    @pytest.mark.asyncio
    async def test_rolls_to_new_statement_on_user_local_closing_day(self, monkeypatch):
        # closing_day=15 and user-local today July 15 -> the July statement just closed.
        _patch_statement_deps(monkeypatch, date(2026, 7, 15))
        card = CreditCard(id=1, user_id=1, name="Test", closing_day=15, due_day=25, currency="ARS")
        statements = await card_reconciliation_service.list_recent_statements(None, card, "ARS")
        # With no reconciliations and no activity, only the latest closed statement survives.
        assert len(statements) == 1
        assert statements[0]["period_end"] == date(2026, 7, 15)

    @pytest.mark.asyncio
    async def test_stays_on_previous_statement_before_user_local_closing_day(self, monkeypatch):
        # One user-local day earlier (e.g. an ART evening that is already July 15 in UTC): the
        # latest closed statement is still June's.
        _patch_statement_deps(monkeypatch, date(2026, 7, 14))
        card = CreditCard(id=1, user_id=1, name="Test", closing_day=15, due_day=25, currency="ARS")
        statements = await card_reconciliation_service.list_recent_statements(None, card, "ARS")
        assert len(statements) == 1
        assert statements[0]["period_end"] == date(2026, 6, 15)


# --- Signed adjustment (the credit fix) ---


class TestSignedAdjustment:
    """A card bucket is `sum(expenses) - sum(settlements)`, so ONLY an expense can move it. Both
    reconciliation directions therefore create one signed, card-linked expense; an income row (the
    previous shape for a credit) left the card overstated because income never enters the bucket."""

    @pytest.mark.asyncio
    async def test_credit_creates_a_negative_card_linked_expense(self, monkeypatch):
        captured = _wire_create(monkeypatch, computed=Decimal("1000"))

        await card_reconciliation_service.create_or_replace(
            AsyncMock(),
            7,
            USER,
            currency="ARS",
            period_start=date(2026, 6, 21),
            period_end=date(2026, 7, 20),
            statement_balance=Decimal("800"),
        )

        expense = captured["expense"]
        assert expense.amount == Decimal("-200")
        assert expense.category == ExpenseCategory.card_credits_and_refunds
        assert expense.credit_card_id == 7
        assert expense.payment_method == "credit_card"
        # A credit clears card debt; it does not deposit cash. Linking an account here would add the
        # amount to a balance as well, double-counting one event.
        assert expense.account_id is None
        assert "income" not in captured

    @pytest.mark.asyncio
    async def test_shortfall_still_creates_a_positive_fee_expense(self, monkeypatch):
        captured = _wire_create(monkeypatch, computed=Decimal("1000"))

        await card_reconciliation_service.create_or_replace(
            AsyncMock(),
            7,
            USER,
            currency="ARS",
            period_start=date(2026, 6, 21),
            period_end=date(2026, 7, 20),
            statement_balance=Decimal("1500"),
        )

        expense = captured["expense"]
        assert expense.amount == Decimal("500")
        assert expense.category == ExpenseCategory.card_fees_and_taxes

    @pytest.mark.asyncio
    async def test_matching_statement_creates_no_adjustment(self, monkeypatch):
        captured = _wire_create(monkeypatch, computed=Decimal("1000"))

        reconciliation = await card_reconciliation_service.create_or_replace(
            AsyncMock(),
            7,
            USER,
            currency="ARS",
            period_start=date(2026, 6, 21),
            period_end=date(2026, 7, 20),
            statement_balance=Decimal("1000"),
        )

        assert "expense" not in captured
        assert reconciliation.adjustment_expense_id is None
        assert reconciliation.adjustment_income_id is None

    def test_a_credit_nets_out_of_the_bucket_sum(self):
        # The end-to-end property the fix exists for: a 1000 expense plus a -200 credit leaves the
        # bucket at 800, matching the statement. cumulative_balances_at is the same arithmetic the
        # live bucket balance uses.
        balances = cumulative_balances_at(
            [date(2026, 7, 20)],
            [(date(2026, 7, 10), Decimal("1000")), (date(2026, 7, 20), Decimal("-200"))],
            [],
        )
        assert balances[date(2026, 7, 20)] == Decimal("800")
