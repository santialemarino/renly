from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import CardBucketBalance
from app.models.credit_card import CreditCard
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.services import finance_metrics_service
from app.utils.metrics import RateLookup, convert_optional


# Every aggregate here now unions the caller's SHARE of their groups' rows, so each one first resolves
# the seats they hold. These tests are about the private arithmetic, so the caller holds none — which is
# also what every solo user holds, and what makes the shared branch of each query not be built at all.
def _solo(monkeypatch) -> None:
    monkeypatch.setattr(finance_metrics_service.group_repository, "list_active_member_ids", AsyncMock(return_value=[]))


def _card(*, card_id: int, is_active: bool) -> CreditCard:
    return CreditCard(id=card_id, user_id=1, name=f"Card {card_id}", closing_day=20, due_day=5, currency="ARS", is_active=is_active)


# --- Archived-card aggregation (archive is a UI filter, not an accounting event) ---


class TestOverviewIncludesArchivedCards:
    @pytest.mark.asyncio
    async def test_card_balance_sums_archived_cards(self, monkeypatch):
        # Active card owes 100, archived card owes 500 — overview liability must be 600.
        cards = [_card(card_id=1, is_active=True), _card(card_id=2, is_active=False)]
        list_mock = AsyncMock(return_value=cards)
        monkeypatch.setattr(finance_metrics_service.credit_card_repository, "list_by_user", list_mock)
        monkeypatch.setattr(finance_metrics_service.income_repository, "sum_by_user_daily", AsyncMock(return_value=[]))
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_daily", AsyncMock(return_value=[]))
        _solo(monkeypatch)
        monkeypatch.setattr(finance_metrics_service.settings_service, "get_user_today", AsyncMock(return_value=date(2026, 6, 15)))
        monkeypatch.setattr(
            finance_metrics_service.credit_card_service,
            "get_card_balances",
            AsyncMock(
                return_value={
                    1: [CardBucketBalance(currency="ARS", balance=Decimal("100"))],
                    2: [CardBucketBalance(currency="ARS", balance=Decimal("500"))],
                }
            ),
        )
        result = await finance_metrics_service.get_overview(AsyncMock(), 1)
        assert result.credit_card_balance == Decimal("600")
        # The aggregation site must query ALL cards explicitly.
        assert list_mock.call_args.kwargs == {"active_only": False}


# --- Previous-period comparison window ---


class TestPrevPeriodWindow:
    @pytest.mark.asyncio
    async def test_prev_window_is_adjacent_and_equal_length(self, monkeypatch):
        # Current window Jun 1-30 2026 (30 days inclusive). Previous must be May 2-31
        # (30 days inclusive) — the old code produced May 3-Jun 1, double-counting Jun 1.
        june, may = date(2026, 6, 5), date(2026, 5, 5)
        income_mock = AsyncMock(side_effect=[[(june, "salary", "ARS", Decimal("1000"))], [(may, "salary", "ARS", Decimal("800"))]])
        expense_mock = AsyncMock(side_effect=[[(june, "food", "ARS", Decimal("400"))], [(may, "food", "ARS", Decimal("500"))]])
        monkeypatch.setattr(finance_metrics_service.income_repository, "sum_by_user_daily", income_mock)
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_daily", expense_mock)
        monkeypatch.setattr(finance_metrics_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
        _solo(monkeypatch)
        monkeypatch.setattr(finance_metrics_service.settings_service, "get_user_today", AsyncMock(return_value=date(2026, 6, 15)))
        result = await finance_metrics_service.get_overview(
            AsyncMock(),
            1,
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 30),
        )
        # Second call on each repo is the previous-period query.
        assert income_mock.call_args_list[1].kwargs == {"date_from": date(2026, 5, 2), "date_to": date(2026, 5, 31)}
        assert expense_mock.call_args_list[1].kwargs == {"date_from": date(2026, 5, 2), "date_to": date(2026, 5, 31)}
        # (1000 - 800) / 800 = 0.25; (400 - 500) / 500 = -0.2.
        assert result.income_change_pct == Decimal("0.25")
        assert result.expense_change_pct == Decimal("-0.2")


# --- Every finance aggregate converts each day at its own rate, and they all agree ---


class TestEveryAggregateConvertsEachDayAtItsOwnRate:
    # Two peso expenses in the SAME month, on days whose rates differ: 10,000 ARS on May 5 at 1,000 is
    # 10 USD, and 12,500 ARS on May 20 at 1,250 is 10 USD, so the month is 20 USD. Converting the month
    # at its last day's rate (the old basis) reads 22,500 / 1,250 = 18 — two dollars short of the rows
    # the /expenses list shows, each at its own date. The totals, the monthly bar, the category donut and
    # the dashboard's own figure must all equal the sum of the converted rows.
    _RATES = {
        ExchangeRatePair.USD_ARS_MEP: [
            ExchangeRate(date=date(2026, 5, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1000"), source="test"),
            ExchangeRate(date=date(2026, 5, 15), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1250"), source="test"),
        ],
    }
    _ROWS = [(date(2026, 5, 5), "food", "ARS", Decimal("10000")), (date(2026, 5, 20), "dining", "ARS", Decimal("12500"))]

    @pytest.mark.asyncio
    async def test_totals_bars_and_donut_equal_the_sum_of_the_converted_rows(self, monkeypatch):
        lookup = RateLookup(dollar_preference="mep", rates_by_pair=self._RATES)
        monkeypatch.setattr(finance_metrics_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))
        monkeypatch.setattr(finance_metrics_service.income_repository, "sum_by_user_daily", AsyncMock(return_value=[]))
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_daily", AsyncMock(return_value=self._ROWS))
        monkeypatch.setattr(finance_metrics_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
        _solo(monkeypatch)
        monkeypatch.setattr(finance_metrics_service.settings_service, "get_user_today", AsyncMock(return_value=date(2026, 6, 30)))

        overview = await finance_metrics_service.get_overview(AsyncMock(), 1, currency="USD")
        monthly = await finance_metrics_service.get_monthly(AsyncMock(), 1, currency="USD")
        donut = await finance_metrics_service.get_expense_breakdown(AsyncMock(), 1, currency="USD")

        # What the list shows: each row converted at its own date, by the same helper the list uses.
        rows = sum((convert_optional(amount, cur, "USD", lookup, day) for day, _cat, cur, amount in self._ROWS), Decimal("0"))
        assert rows == Decimal("20.00")
        assert overview.total_expenses == rows
        assert [(p.date, p.expenses) for p in monthly.points] == [(date(2026, 5, 1), rows)]
        assert donut.total_expenses == rows
        assert {item.category: item.value for item in donut.items} == {"food": Decimal("10.00"), "dining": Decimal("10.00")}


# --- Uncategorized slice flows through the breakdown ---


class TestUncategorizedSlice:
    @pytest.mark.asyncio
    async def test_expense_breakdown_includes_uncategorized(self, monkeypatch):
        # 3000 uncategorized + 1000 food = 4000 total -> 75% / 25%. Before the schema
        # widening this raised a validation error ('uncategorized' is not an enum member).
        rows = [(date(2026, 6, 1), "food", "ARS", Decimal("1000")), (date(2026, 6, 2), "uncategorized", "ARS", Decimal("3000"))]
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_daily", AsyncMock(return_value=rows))
        _solo(monkeypatch)
        monkeypatch.setattr(finance_metrics_service.settings_service, "get_user_today", AsyncMock(return_value=date(2026, 6, 15)))
        result = await finance_metrics_service.get_expense_breakdown(AsyncMock(), 1)
        assert result.total_expenses == Decimal("4000")
        assert [(i.category, i.value, i.percentage) for i in result.items] == [
            ("uncategorized", Decimal("3000"), Decimal("75")),
            ("food", Decimal("1000"), Decimal("25")),
        ]


# A card credit posts a negative reconciliation adjustment, so a category can total below zero. The
# headline total keeps it (net spending is the honest figure), but percentages are computed against
# the positive categories only — a share of a mixed-sign total is meaningless, and the donut this
# feeds cannot draw a negative slice.
class TestNegativeCategoryInBreakdown:
    @pytest.mark.asyncio
    async def test_negative_category_is_kept_in_the_total_but_scored_zero_percent(self, monkeypatch):
        # 1000 food + 3000 rent - 200 card credit = 3800 net; shares are of the 4000 positive side.
        rows = [
            (date(2026, 6, 1), "food", "ARS", Decimal("1000")),
            (date(2026, 6, 1), "rent", "ARS", Decimal("3000")),
            (date(2026, 6, 2), "card_credits_and_refunds", "ARS", Decimal("-200")),
        ]
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_daily", AsyncMock(return_value=rows))
        _solo(monkeypatch)
        monkeypatch.setattr(finance_metrics_service.settings_service, "get_user_today", AsyncMock(return_value=date(2026, 6, 15)))

        result = await finance_metrics_service.get_expense_breakdown(AsyncMock(), 1)

        assert result.total_expenses == Decimal("3800")
        assert [(i.category, i.value, i.percentage) for i in result.items] == [
            ("rent", Decimal("3000"), Decimal("75")),
            ("food", Decimal("1000"), Decimal("25")),
            ("card_credits_and_refunds", Decimal("-200"), Decimal("0")),
        ]
        # Positive shares still sum to 100 — the negative row never distorts them.
        assert sum(i.percentage for i in result.items) == Decimal("100")

    @pytest.mark.asyncio
    async def test_all_negative_categories_yield_zero_percentages_without_dividing_by_zero(self, monkeypatch):
        rows = [(date(2026, 6, 2), "card_credits_and_refunds", "ARS", Decimal("-200"))]
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_daily", AsyncMock(return_value=rows))
        _solo(monkeypatch)
        monkeypatch.setattr(finance_metrics_service.settings_service, "get_user_today", AsyncMock(return_value=date(2026, 6, 15)))

        result = await finance_metrics_service.get_expense_breakdown(AsyncMock(), 1)

        assert result.total_expenses == Decimal("-200")
        assert [(i.category, i.percentage) for i in result.items] == [("card_credits_and_refunds", Decimal("0"))]
