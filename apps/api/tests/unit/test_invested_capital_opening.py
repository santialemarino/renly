from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.investment import Investment, InvestmentCategory
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services import metrics_service
from app.utils.metrics import RateLookup, unexplained_opening

# A holding recorded only through snapshots — or opened with a value before its first recorded deposit —
# came in with capital no transaction states: its first snapshot. The TWR and the IRR already count that
# snapshot as contributed capital; invested capital, the gain and the simple return now do too, so such a
# holding no longer reads its whole value as gain. A holding whose opening a transaction DOES explain (a
# deposit on or before the first snapshot) keeps exactly the figures it had.

_TODAY = date(2026, 3, 20)
_RATES = {
    ExchangeRatePair.USD_ARS_MEP: [
        ExchangeRate(date=date(2026, 1, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1000"), source="test"),
        ExchangeRate(date=date(2026, 3, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("2000"), source="test"),
    ],
}


def _snap(inv_id: int, d: date, value: str) -> InvestmentSnapshot:
    return InvestmentSnapshot(investment_id=inv_id, user_id=1, date=d, value=Decimal(value), currency="USD")


def _tx(inv_id: int, d: date, amount: str) -> Transaction:
    return Transaction(investment_id=inv_id, user_id=1, date=d, amount=Decimal(amount), currency="USD", type=TransactionType.deposit)


# 1: no transaction at all (worth 1,000 → 50). 2: valued at 500, then 200 deposited later (→ 760).
# 3: a deposit ON its first snapshot's day explains its opening (1,000 → 1,100).
_SNAPS = [
    _snap(1, date(2026, 1, 10), "1000"),
    _snap(1, date(2026, 2, 10), "50"),
    _snap(2, date(2026, 1, 10), "500"),
    _snap(2, date(2026, 2, 10), "760"),
    _snap(3, date(2026, 1, 10), "1000"),
    _snap(3, date(2026, 2, 10), "1100"),
]
_TXS = [_tx(2, date(2026, 2, 1), "200"), _tx(3, date(2026, 1, 10), "1000")]


@pytest.fixture
def wired(monkeypatch):
    repo = metrics_service.metrics_repository
    holdings = [Investment(id=i, user_id=1, name=f"H{i}", category=InvestmentCategory.cedears, base_currency="USD") for i in (1, 2, 3)]

    async def snapshots(_session, ids):
        return [s for s in _SNAPS if s.investment_id in ids]

    async def transactions(_session, ids):
        return [t for t in _TXS if t.investment_id in ids]

    async def by_id(_session, investment_id, _user_id):
        return next(h for h in holdings if h.id == investment_id)

    monkeypatch.setattr(repo, "list_active_investments", AsyncMock(return_value=holdings))
    monkeypatch.setattr(repo, "list_snapshots_by_investments", snapshots)
    monkeypatch.setattr(repo, "list_transactions_by_investments", transactions)
    monkeypatch.setattr(metrics_service.investment_repository, "get_by_id", by_id)
    lookup = RateLookup(dollar_preference="mep", rates_by_pair=_RATES)
    monkeypatch.setattr(metrics_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))
    monkeypatch.setattr(metrics_service.settings_service, "get_user_today", AsyncMock(return_value=_TODAY))


class TestUnexplainedOpening:
    def test_a_holding_with_no_transactions_opens_with_its_first_snapshot(self):
        assert unexplained_opening([_SNAPS[0], _SNAPS[1]], []) is _SNAPS[0]

    def test_a_later_deposit_does_not_explain_the_opening(self):
        assert unexplained_opening([_SNAPS[2], _SNAPS[3]], [_TXS[0]]) is _SNAPS[2]

    def test_a_transaction_on_the_first_snapshots_day_explains_it(self):
        assert unexplained_opening([_SNAPS[4], _SNAPS[5]], [_TXS[1]]) is None

    def test_no_snapshot_no_opening(self):
        assert unexplained_opening([], [_TXS[0]]) is None


@pytest.mark.usefixtures("wired")
class TestTheOpeningCountsAsCapital:
    @pytest.mark.asyncio
    async def test_the_investment_detail(self):
        no_deposits = await metrics_service.get_investment_metrics(AsyncMock(), 1, 1)
        assert no_deposits.invested_capital == Decimal("1000")
        assert no_deposits.absolute_gain == Decimal("-950")
        assert no_deposits.simple_return == Decimal("-0.95")
        later_deposit = await metrics_service.get_investment_metrics(AsyncMock(), 2, 1)
        assert later_deposit.invested_capital == Decimal("700")
        assert later_deposit.absolute_gain == Decimal("60")
        explained = await metrics_service.get_investment_metrics(AsyncMock(), 3, 1)
        assert explained.invested_capital == Decimal("1000")
        assert explained.absolute_gain == Decimal("100")

    @pytest.mark.asyncio
    async def test_the_summary_and_the_portfolio(self):
        summary = {i.investment_id: i for i in (await metrics_service.get_investments_summary(AsyncMock(), 1)).items}
        assert [(summary[i].invested_capital, summary[i].absolute_gain) for i in (1, 2, 3)] == [
            (Decimal("1000"), Decimal("-950")),
            (Decimal("700"), Decimal("60")),
            (Decimal("1000"), Decimal("100")),
        ]
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.total_invested == Decimal("2700")
        assert portfolio.absolute_gain == Decimal("-790")

    @pytest.mark.asyncio
    async def test_the_opening_converts_at_its_own_date(self):
        # In pesos: the 1,000 USD opening entered on Jan 10 at 1,000 — 1,000,000 ARS — while the 50 USD it
        # is worth now converts at today's 2,000.
        detail = await metrics_service.get_investment_metrics(AsyncMock(), 1, 1, currency="ARS")
        assert detail.invested_capital == Decimal("1000000.00")
        assert detail.current_value == Decimal("100000.00")
        summary = {i.investment_id: i for i in (await metrics_service.get_investments_summary(AsyncMock(), 1, currency="ARS")).items}
        assert summary[1].invested_capital == Decimal("1000000.00")
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="ARS")
        # 1,000,000 + (500,000 opening + 200,000 deposit) + 1,000,000, every flow at January's 1,000.
        assert portfolio.total_invested == Decimal("2700000.00")
