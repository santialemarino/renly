from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import CardReconciliationFuturePeriodError
from app.domain.credit_card import CardBucketBalance
from app.models.card_reconciliation import CardReconciliation
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseCategory
from app.models.user import User
from app.services import card_reconciliation_service, credit_card_service
from app.services.card_reconciliation_service import compute_reconciliation_difference, cumulative_balances_at

USER = User(id=1, email="user@test", password_hash="x", session_epoch=0)


# Wires create_or_replace's dependencies: an owned card, a fixed computed balance, and a
# capture-and-assign-id fake for the adjustment row the service writes. "Today" sits well after the
# periods these tests use, so the future-period guard never fires; the stale hook is stubbed out
# because TestStalePropagation exercises it directly.
def _wire_create(monkeypatch, *, computed, today=date(2026, 12, 31)):
    captured: dict = {}
    card = CreditCard(id=7, user_id=1, name="Visa", closing_day=20, due_day=28, currency="ARS")
    monkeypatch.setattr(card_reconciliation_service, "_get_card_or_404", AsyncMock(return_value=card))
    monkeypatch.setattr(card_reconciliation_service.settings_service, "get_user_today", AsyncMock(return_value=today))
    monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", AsyncMock())
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

    def test_negative_difference_is_a_credit(self):
        # Bank says 900, app computed 1000 -> -100 (credit / refund the app missed). Becomes a
        # negative, card-linked expense — never an income row, which could not move the bucket.
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


# A card bucket is `sum(expenses) - sum(settlements)`, so ONLY an expense can move it. Both
# reconciliation directions therefore create one signed, card-linked expense; an income row (the
# previous shape for a credit) left the card overstated because income never enters the bucket.
class TestSignedAdjustment:
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
        # bucket at 800, matching the statement. cumulative_balances_at backs list_recent_statements.
        balances = cumulative_balances_at(
            [date(2026, 7, 20)],
            [(date(2026, 7, 10), Decimal("1000")), (date(2026, 7, 20), Decimal("-200"))],
            [],
        )
        assert balances[date(2026, 7, 20)] == Decimal("800")

    def test_a_credit_nets_out_of_the_balance_the_product_reads(self):
        # cumulative_balances_at (above) only backs the statements list. The bucket balance the
        # credit-cards page, net worth, the composition donut and the payments calendar all read is
        # compute_card_balances — and it is the one path that round-trips the grouped sum through
        # float(), so assert the sign survives there too. 1000 + (-200) => 800.
        balances = credit_card_service.compute_card_balances(
            [7],
            {7: "ARS"},
            {7: {"ARS": 800.0}},
            {},
        )
        assert balances[7] == [CardBucketBalance(currency="ARS", balance=Decimal("800"))]

    @pytest.mark.asyncio
    async def test_bucket_balance_at_subtracts_a_credit(self, monkeypatch):
        # compute_bucket_balance_at is what reconciliation itself records as computed_balance, so a
        # credit inside the period must already be netted out of it.
        monkeypatch.setattr(
            card_reconciliation_service.card_reconciliation_repository,
            "sum_expenses_at",
            AsyncMock(return_value=Decimal("800")),
        )
        monkeypatch.setattr(
            card_reconciliation_service.card_reconciliation_repository,
            "sum_settlements_at",
            AsyncMock(return_value=Decimal("0")),
        )

        balance = await card_reconciliation_service.compute_bucket_balance_at(AsyncMock(), 7, "ARS", date(2026, 7, 20))

        assert balance == Decimal("800")


# --- Staleness: the predicate, and propagation from the reconciliation's own writes ---


# Builds fake reconciliation rows for a bucket. Only the fields the stale path reads are set.
def _rec(rec_id: int, period_start: date, period_end: date, *, is_stale: bool = False) -> CardReconciliation:
    return CardReconciliation(
        id=rec_id,
        user_id=1,
        card_id=7,
        currency="ARS",
        period_start=period_start,
        period_end=period_end,
        statement_balance=Decimal("0"),
        computed_balance=Decimal("0"),
        difference=Decimal("0"),
        is_stale=is_stale,
    )


class TestStalePredicate:
    # A bucket balance is every row dated <= period_end, from the beginning of history — the period
    # bounds only name WHICH statement. So an edit dated before a reconciled period still moves that
    # period's balance, which the old period-contains predicate missed: the measured symptom was a
    # reconciled balance drifting 1000 -> 900 with is_stale still false.
    @pytest.mark.asyncio
    async def test_an_edit_before_the_period_still_marks_it_stale(self, monkeypatch):
        december = _rec(2, date(2026, 11, 21), date(2026, 12, 20))
        captured: dict = {}

        async def fake_list(_session, card_id, currency, target_date):
            captured["target_date"] = target_date
            # Stand in for the real query: December's period_end is after the edited date.
            return [december] if december.period_end >= target_date else []

        monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "list_affected_by_date", fake_list)
        mark = AsyncMock()
        monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "mark_stale", mark)

        await card_reconciliation_service.mark_stale_for_date(AsyncMock(), 7, "ARS", date(2026, 10, 10))

        assert captured["target_date"] == date(2026, 10, 10)
        assert mark.await_args.args[1] == [2]

    @pytest.mark.asyncio
    async def test_an_edit_after_every_period_marks_nothing(self, monkeypatch):
        monkeypatch.setattr(
            card_reconciliation_service.card_reconciliation_repository,
            "list_affected_by_date",
            AsyncMock(return_value=[]),
        )
        mark = AsyncMock()
        monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "mark_stale", mark)

        await card_reconciliation_service.mark_stale_for_date(AsyncMock(), 7, "ARS", date(2027, 1, 1))

        mark.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_already_stale_row_is_not_re_marked(self, monkeypatch):
        monkeypatch.setattr(
            card_reconciliation_service.card_reconciliation_repository,
            "list_affected_by_date",
            AsyncMock(return_value=[_rec(2, date(2026, 11, 21), date(2026, 12, 20), is_stale=True)]),
        )
        mark = AsyncMock()
        monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "mark_stale", mark)

        await card_reconciliation_service.mark_stale_for_date(AsyncMock(), 7, "ARS", date(2026, 10, 10))

        mark.assert_not_awaited()


class TestStalePropagation:
    # Reconciling an OLDER period posts an adjustment dated at its period_end, which lands inside every
    # later period's balance. Those later rows keep rendering their recorded difference as valid, so
    # they must be flagged. This is the case the account feature refuses outright; cards allow it and
    # propagate staleness instead, because re-running a period here replaces it cleanly.
    @pytest.mark.asyncio
    async def test_reconciling_an_older_period_flags_the_later_ones(self, monkeypatch):
        _wire_create(monkeypatch, computed=Decimal("1000"))
        stale = AsyncMock()
        monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", stale)

        await card_reconciliation_service.create_or_replace(
            AsyncMock(),
            7,
            USER,
            currency="ARS",
            period_start=date(2026, 9, 21),
            period_end=date(2026, 10, 20),
            statement_balance=Decimal("1050"),
        )

        # Keyed on this period's own period_end: the row is not written yet and any prior was already
        # deleted, so period_end >= period_end reaches strictly later periods only.
        assert stale.await_args.args[1:] == (7, "ARS", date(2026, 10, 20))

    @pytest.mark.asyncio
    async def test_the_fresh_row_is_not_born_stale(self, monkeypatch):
        captured = _wire_create(monkeypatch, computed=Decimal("1000"))

        await card_reconciliation_service.create_or_replace(
            AsyncMock(),
            7,
            USER,
            currency="ARS",
            period_start=date(2026, 9, 21),
            period_end=date(2026, 10, 20),
            statement_balance=Decimal("1050"),
        )

        assert captured["reconciliation"].is_stale is False

    @pytest.mark.asyncio
    async def test_deleting_a_reconciliation_flags_the_later_ones(self, monkeypatch):
        # The cascade drops its adjustment, so a dated row vanishes from every balance that summed it.
        rec = _rec(2, date(2026, 9, 21), date(2026, 10, 20))
        monkeypatch.setattr(card_reconciliation_service, "get_reconciliation", AsyncMock(return_value=rec))
        monkeypatch.setattr(card_reconciliation_service.card_reconciliation_repository, "delete", AsyncMock())
        stale = AsyncMock()
        monkeypatch.setattr(card_reconciliation_service, "mark_stale_for_date", stale)
        session = AsyncMock()

        await card_reconciliation_service.delete_reconciliation(session, 7, 2, USER)

        assert stale.await_args.args[1:] == (7, "ARS", date(2026, 10, 20))
        # Flushed before the hook runs, or the row being deleted would match its own predicate.
        assert session.flush.await_count == 1
        session.commit.assert_awaited_once()


class TestFuturePeriodGuard:
    # A statement period that has not closed yet has no statement to reconcile against. This is the one
    # rule the card and account flows deliberately share.
    @pytest.mark.asyncio
    async def test_a_period_closing_after_today_is_rejected(self, monkeypatch):
        _wire_create(monkeypatch, computed=Decimal("1000"), today=date(2026, 7, 1))

        with pytest.raises(CardReconciliationFuturePeriodError):
            await card_reconciliation_service.create_or_replace(
                AsyncMock(),
                7,
                USER,
                currency="ARS",
                period_start=date(2026, 6, 21),
                period_end=date(2026, 7, 20),
                statement_balance=Decimal("1000"),
            )

    @pytest.mark.asyncio
    async def test_a_period_closing_today_is_accepted(self, monkeypatch):
        captured = _wire_create(monkeypatch, computed=Decimal("1000"), today=date(2026, 7, 20))

        await card_reconciliation_service.create_or_replace(
            AsyncMock(),
            7,
            USER,
            currency="ARS",
            period_start=date(2026, 6, 21),
            period_end=date(2026, 7, 20),
            statement_balance=Decimal("1200"),
        )

        assert captured["reconciliation"].period_end == date(2026, 7, 20)
