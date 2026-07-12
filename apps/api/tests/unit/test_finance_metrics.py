from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import CardBucketBalance
from app.models.credit_card import CreditCard
from app.services import finance_metrics_service


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
        monkeypatch.setattr(finance_metrics_service.income_repository, "sum_by_user", AsyncMock(return_value={}))
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user", AsyncMock(return_value={}))
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
        income_mock = AsyncMock(side_effect=[{"ARS": 1000.0}, {"ARS": 800.0}])
        expense_mock = AsyncMock(side_effect=[{"ARS": 400.0}, {"ARS": 500.0}])
        monkeypatch.setattr(finance_metrics_service.income_repository, "sum_by_user", income_mock)
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user", expense_mock)
        monkeypatch.setattr(finance_metrics_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
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


# --- Uncategorized slice flows through the breakdown ---


class TestUncategorizedSlice:
    @pytest.mark.asyncio
    async def test_expense_breakdown_includes_uncategorized(self, monkeypatch):
        # 3000 uncategorized + 1000 food = 4000 total -> 75% / 25%. Before the schema
        # widening this raised a validation error ('uncategorized' is not an enum member).
        rows = [("food", "ARS", 1000.0), ("uncategorized", "ARS", 3000.0)]
        monkeypatch.setattr(finance_metrics_service.expense_repository, "sum_by_user_grouped_by_category", AsyncMock(return_value=rows))
        result = await finance_metrics_service.get_expense_breakdown(AsyncMock(), 1)
        assert result.total_expenses == Decimal("4000")
        assert [(i.category, i.value, i.percentage) for i in result.items] == [
            ("uncategorized", Decimal("3000"), Decimal("75")),
            ("food", Decimal("1000"), Decimal("25")),
        ]
