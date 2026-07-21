from datetime import date as date_type
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import CardBucketBalance
from app.models.account import Account, AccountType
from app.models.credit_card import CreditCard
from app.models.investment import InvestmentCategory
from app.schemas.metrics import AllocationItem, AllocationResponse, SkippedInvestment
from app.services import dashboard_service, exchange_rate_service, settings_service
from app.services.dashboard_service import (
    compute_cash_total,
    compute_monthly_card_balances,
    compute_monthly_cash_balances,
    forward_fill_card_balances,
)

# Rate map: 1 USD = 1200 ARS.
RATE_MAP = {
    "USD": Decimal("1"),
    "ARS": Decimal("1200"),
}


# Stub RateLookup that returns the same rate map for any date — keeps the existing tests focused
# on the per-currency aggregation logic rather than the date-aware lookup behaviour (which has
# its own coverage in test_metrics_helpers / test_rate_lookup).
class _FixedLookup:
    def __init__(self, rate_map: dict[str, Decimal] | None) -> None:
        self._rate_map = rate_map

    def get_rate_map_at(self, _as_of_date: date_type) -> dict[str, Decimal] | None:
        return self._rate_map


FIXED_LOOKUP = _FixedLookup(RATE_MAP)


# --- compute_monthly_card_balances (5-tuple settlement / expense shape) ---


class TestComputeMonthlyCardBalances:
    def test_single_card_single_currency(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 2, "USD", 50.0),
        ]
        settlements = [
            (1, 2026, 2, "USD", 80.0),
        ]
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # Jan: 100 - 0 = 100. Feb: 100 + 50 - 80 = 70.
        assert result[(2026, 1)] == Decimal("100")
        assert result[(2026, 2)] == Decimal("70")
        assert skipped == []

    def test_multi_card_multi_currency_converts_each_bucket(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (2, 2026, 1, "ARS", 1200.0),  # 1200 ARS = 1 USD.
        ]
        settlements = []
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD", 2: "ARS"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # 100 USD + (1200 ARS -> 1 USD) = 101 USD.
        assert result[(2026, 1)] == Decimal("101")
        assert skipped == []

    def test_cumulative_across_months(self):
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 3, "USD", 50.0),
        ]
        settlements = []
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # Jan: 100. Mar: 100 + 50 = 150. Feb has no data, not in result.
        assert result[(2026, 1)] == Decimal("100")
        assert (2026, 2) not in result
        assert result[(2026, 3)] == Decimal("150")
        assert skipped == []

    def test_settlement_exceeds_expenses(self):
        expenses = [(1, 2026, 1, "USD", 50.0)]
        settlements = [(1, 2026, 1, "USD", 100.0)]
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # Overpayment: 50 - 100 = -50.
        assert result[(2026, 1)] == Decimal("-50")
        assert skipped == []

    def test_empty_inputs(self):
        result, skipped = compute_monthly_card_balances(
            [],
            [],
            card_currencies={},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        assert result == {}
        assert skipped == []

    def test_no_target_currency_passes_values_through(self):
        # When no target currency is set, every bucket's value is summed raw.
        expenses = [
            (1, 2026, 1, "USD", 100.0),
            (1, 2026, 1, "ARS", 500.0),
        ]
        settlements = []
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency=None,
            lookup=None,
        )
        # No conversion: 100 + 500 = 600.
        assert result[(2026, 1)] == Decimal("600")
        assert skipped == []

    def test_foreign_bucket_settled_in_its_own_currency(self):
        # ARS card with USD bucket activity — both expense and settlement live in USD,
        # so the USD bucket cancels cleanly without going through card currency.
        expenses = [(1, 2026, 1, "USD", 50.0)]
        settlements = [(1, 2026, 1, "USD", 50.0)]
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "ARS"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        assert result[(2026, 1)] == Decimal("0")
        assert skipped == []

    def test_each_bucket_converts_from_its_own_currency(self):
        # ARS-currency settlement on a USD card converts directly from ARS, not via card currency.
        expenses = [(1, 2026, 1, "USD", 100.0)]
        settlements = [(1, 2026, 1, "ARS", 1200.0)]  # 1200 ARS = 1 USD.
        result, skipped = compute_monthly_card_balances(
            expenses,
            settlements,
            card_currencies={1: "USD"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        # 100 USD expense - 1 USD settlement (from 1200 ARS) = 99 USD.
        assert result[(2026, 1)] == Decimal("99")
        assert skipped == []

    def test_missing_rate_row_is_skipped_and_reported(self):
        # FIXED_LOOKUP maps only USD/ARS — the EUR expense row must be excluded, not passed through.
        result, skipped = compute_monthly_card_balances(
            [(1, 2026, 1, "ARS", 1200.0), (1, 2026, 1, "EUR", 50.0)],
            [],
            card_currencies={1: "ARS"},
            target_currency="USD",
            lookup=FIXED_LOOKUP,
        )
        assert skipped == ["EUR"]
        # 1200 ARS -> 1 USD at the fake rate; EUR contributes nothing.
        assert result[(2026, 1)] == Decimal("1")


# --- forward_fill_card_balances ---


class TestForwardFillCardBalances:
    def test_months_after_activity_keep_prior_balance(self):
        # Card ran up 500 in Oct 2025; portfolio window starts Jan 2026 with no card
        # activity. Old merge read 0 for Jan/Feb — the outstanding 500 must persist.
        balances = forward_fill_card_balances(
            [(2026, 1), (2026, 2)],
            {(2025, 10): Decimal("500")},
        )
        assert balances == [Decimal("500"), Decimal("500")]

    def test_gap_months_between_activity_forward_fill(self):
        balances = forward_fill_card_balances(
            [(2026, 1), (2026, 2), (2026, 3), (2026, 4)],
            {(2026, 1): Decimal("100"), (2026, 3): Decimal("150")},
        )
        assert balances == [Decimal("100"), Decimal("100"), Decimal("150"), Decimal("150")]

    def test_months_before_first_activity_read_zero(self):
        balances = forward_fill_card_balances(
            [(2026, 1), (2026, 2), (2026, 3)],
            {(2026, 3): Decimal("100")},
        )
        assert balances == [Decimal("0"), Decimal("0"), Decimal("100")]

    def test_empty_activity_reads_zero(self):
        assert forward_fill_card_balances([(2026, 1)], {}) == [Decimal("0")]


# --- get_composition percentage base ---


CAT_A, CAT_B = list(InvestmentCategory)[:2]


def _allocation() -> AllocationResponse:
    return AllocationResponse(
        items=[
            AllocationItem(category=CAT_A, value=Decimal("600"), percentage=Decimal("60")),
            AllocationItem(category=CAT_B, value=Decimal("400"), percentage=Decimal("40")),
        ],
        total_value=Decimal("1000"),
    )


class TestCompositionPercentages:
    def _patch(self, monkeypatch, *, balance: Decimal) -> None:
        card = CreditCard(id=1, user_id=1, name="Visa", closing_day=20, due_day=5, currency="ARS", is_active=True)
        monkeypatch.setattr(dashboard_service.metrics_service, "get_allocation", AsyncMock(return_value=_allocation()))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[card]))
        monkeypatch.setattr(
            dashboard_service.credit_card_service,
            "get_card_balances",
            AsyncMock(return_value={1: [CardBucketBalance(currency="ARS", balance=balance)]}),
        )
        # No accounts → cash total is 0 (these tests assert the card/asset percentages only).
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=[]))

    @pytest.mark.asyncio
    async def test_negative_card_balance_excluded_from_base(self, monkeypatch):
        # Net credit of 100: old code divided by 900 (60/40 became 66.67/44.44, sum 111%).
        # New base is the displayed items alone (1000) -> exactly 60 / 40.
        self._patch(monkeypatch, balance=Decimal("-100"))
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert [i.percentage for i in result.items] == [Decimal("60"), Decimal("40")]
        assert [i.label for i in result.items] == [CAT_A, CAT_B]
        assert result.total_liabilities == Decimal("-100")

    @pytest.mark.asyncio
    async def test_positive_card_balance_unchanged_base(self, monkeypatch):
        # 600 + 400 assets + 250 liability -> base 1250: 48 / 32 / 20 (identical to old).
        self._patch(monkeypatch, balance=Decimal("250"))
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert [(i.label, i.percentage) for i in result.items] == [
            (CAT_A, Decimal("48")),
            (CAT_B, Decimal("32")),
            ("liabilities", Decimal("20")),
        ]

    @pytest.mark.asyncio
    async def test_asset_side_skipped_currency_surfaced(self, monkeypatch):
        # Fail-loud: an investment whose base currency can't reach the display currency is excluded
        # from total_assets AND its currency is surfaced in skipped_currencies (previously the
        # dashboard flagged only liability-side skips, silently dropping inconvertible assets).
        allocation = AllocationResponse(
            items=[AllocationItem(category=CAT_A, value=Decimal("600"), percentage=Decimal("100"))],
            total_value=Decimal("600"),
            skipped_investments=[SkippedInvestment(investment_id=9, name="Petrobras", base_currency="BRL")],
        )
        monkeypatch.setattr(dashboard_service.metrics_service, "get_allocation", AsyncMock(return_value=allocation))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(settings_service, "get_request_settings", AsyncMock(return_value=settings_service.RequestSettings("mep", None, 50)))
        monkeypatch.setattr(exchange_rate_service, "build_rate_lookup", AsyncMock(return_value=_FixedLookup(RATE_MAP)))

        result = await dashboard_service.get_composition(AsyncMock(), 1, currency="USD")

        assert "BRL" in result.skipped_currencies


# --- Cash helpers (Bucket 3 #1, PR 3) ---


def _acct(account_id: int, currency: str, opening: str = "0", opening_date: date_type = date_type(2026, 1, 1)) -> Account:
    return Account(
        id=account_id,
        user_id=1,
        name=f"Acc {account_id}",
        type=AccountType.bank,
        currency=currency,
        opening_balance=Decimal(opening),
        opening_date=opening_date,
    )


class TestComputeCashTotal:
    def test_converts_and_sums_at_today_rate(self):
        accounts = [_acct(1, "ARS"), _acct(2, "USD")]
        balances = {1: Decimal("1000"), 2: Decimal("10")}
        # Display ARS: 1000 + (10 USD -> 12000 ARS) = 13000.
        total, skipped = compute_cash_total(accounts, balances, "ARS", RATE_MAP)
        assert total == Decimal("13000")
        assert skipped == set()

    def test_unconvertible_currency_skipped(self):
        accounts = [_acct(1, "ARS"), _acct(2, "EUR")]
        balances = {1: Decimal("1000"), 2: Decimal("5")}
        total, skipped = compute_cash_total(accounts, balances, "ARS", RATE_MAP)
        assert total == Decimal("1000")
        assert skipped == {"EUR"}

    def test_zero_balance_never_flags_currency(self):
        accounts = [_acct(1, "EUR")]
        total, skipped = compute_cash_total(accounts, {1: Decimal("0")}, "ARS", RATE_MAP)
        assert total == Decimal("0")
        assert skipped == set()

    def test_no_conversion_when_currency_none(self):
        accounts = [_acct(1, "ARS"), _acct(2, "USD")]
        balances = {1: Decimal("1000"), 2: Decimal("10")}
        total, skipped = compute_cash_total(accounts, balances, None, None)
        assert total == Decimal("1010")
        assert skipped == set()


class TestComputeMonthlyCashBalances:
    def test_accumulates_opening_income_and_expenses(self):
        accounts = [_acct(1, "ARS", opening="1000", opening_date=date_type(2026, 1, 15))]
        income = [(1, 2026, 2, Decimal("500"))]
        expense = [(1, 2026, 3, Decimal("200"))]
        result, skipped = compute_monthly_cash_balances(accounts, income, expense, [], None, None)
        assert result == {(2026, 1): Decimal("1000"), (2026, 2): Decimal("1500"), (2026, 3): Decimal("1300")}
        assert skipped == []

    def test_settlements_reduce_balance(self):
        accounts = [_acct(1, "ARS", opening="1000", opening_date=date_type(2026, 1, 1))]
        result, _ = compute_monthly_cash_balances(accounts, [], [], [(1, 2026, 2, Decimal("300"))], None, None)
        assert result == {(2026, 1): Decimal("1000"), (2026, 2): Decimal("700")}
