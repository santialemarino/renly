from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.investment import Investment, InvestmentCategory
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services import metrics_service

# The portfolio endpoint's headline figures, driven through the service with the repositories answering
# from a fixture — one dollar holding, so no conversion is involved and every figure is the arithmetic
# under test.


def _snap(d: date, value: str) -> InvestmentSnapshot:
    return InvestmentSnapshot(investment_id=1, user_id=1, date=d, value=Decimal(value), currency="USD")


def _wire(monkeypatch, snapshots: list[InvestmentSnapshot], transactions: list[Transaction], today: date) -> None:
    repo = metrics_service.metrics_repository
    holding = Investment(id=1, user_id=1, name="SPY", category=InvestmentCategory.cedears, base_currency="USD")
    monkeypatch.setattr(repo, "list_active_investments", AsyncMock(return_value=[holding]))
    monkeypatch.setattr(repo, "list_snapshots_by_investments", AsyncMock(return_value=snapshots))
    monkeypatch.setattr(repo, "list_transactions_by_investments", AsyncMock(return_value=transactions))
    monkeypatch.setattr(metrics_service.settings_service, "get_user_today", AsyncMock(return_value=today))


def _deposit(d: date, amount: str) -> Transaction:
    return Transaction(investment_id=1, user_id=1, date=d, amount=Decimal(amount), currency="USD", type=TransactionType.deposit)


class TestTheWindowedTwrChainsOnlyThePeriodsInsideTheWindow:
    @pytest.mark.asyncio
    async def test_year_to_date_leaves_out_the_period_ending_on_jan_1(self, monkeypatch):
        # December earned +30% (100 on Dec 1, 20 deposited Dec 10, 150 on Jan 1); January +2% (153 on
        # Feb 1). The year-to-date TWR is January's 2%, not the +32.6% a chain including December reads.
        snaps = [_snap(date(2025, 12, 1), "100"), _snap(date(2026, 1, 1), "150"), _snap(date(2026, 2, 1), "153")]
        _wire(monkeypatch, snaps, [_deposit(date(2025, 12, 10), "20")], date(2026, 2, 10))
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, start_date=date(2026, 1, 1))
        assert response.twr == Decimal("0.02")

    @pytest.mark.asyncio
    async def test_money_moved_in_before_the_start_is_held_at_the_start(self, monkeypatch):
        # 100 valued Dec 15, 50 deposited Dec 20, 160 on Jan 15 and 168 on Feb 15. On Jan 1 the portfolio
        # held 150 — the snapshot plus the deposit no snapshot has seen yet — so the year's gain is 18,
        # not 68, and its TWR (160/150)·(168/160) − 1 = 12%.
        snaps = [_snap(date(2025, 12, 15), "100"), _snap(date(2026, 1, 15), "160"), _snap(date(2026, 2, 15), "168")]
        _wire(monkeypatch, snaps, [_deposit(date(2025, 12, 20), "50")], date(2026, 2, 20))
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, start_date=date(2026, 1, 1))
        assert response.twr == Decimal("0.12")
        assert response.total_invested == Decimal("0")
        assert response.absolute_gain == Decimal("18")
