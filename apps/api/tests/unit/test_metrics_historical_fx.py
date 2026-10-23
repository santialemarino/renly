from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.investment import Investment, InvestmentCategory
from app.models.investment_collection import InvestmentCollection
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services import metrics_service
from app.utils.metrics import RateLookup

# Every investment endpoint converts each row at the rate in force ON ITS OWN DATE — a snapshot at its
# date, a transaction at its date, a month of the evolution chart at the date of the snapshot it carries
# forward — never at today's rate. Converting history at today's rate restates the past in today's
# money: a peso holding that kept its dollar value while the peso fell shows a dollar gain that never
# happened. The six metrics endpoints each walk their own rows, so each is pinned here on its own.
#
# The fixture is built so the two answers cannot coincide. The peso holding is worth exactly 100 USD at
# every snapshot (100,000 ARS at 1,000 in January, 125,000 ARS at 1,250 in February), and the last stored
# rate — the one "today" resolves to — is 2,000. At historical rates it has neither gained nor lost a
# dollar; at today's rate it shows 50 USD of capital grown to 62.50. A dollar holding first valued in
# March sits beside it, so the evolution chart has a month in which the peso holding is CARRIED FORWARD
# and must still be converted at its February snapshot's rate rather than at the month's.

_ARS, _USD = 1, 2

_RATES = {
    ExchangeRatePair.USD_ARS_MEP: [
        ExchangeRate(date=date(2026, 1, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1000"), source="test"),
        ExchangeRate(date=date(2026, 2, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1250"), source="test"),
        ExchangeRate(date=date(2026, 3, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("2000"), source="test"),
    ],
}

_INVESTMENTS = [
    Investment(id=_ARS, user_id=1, name="Merval", category=InvestmentCategory.stocks, base_currency="ARS"),
    Investment(id=_USD, user_id=1, name="SPY", category=InvestmentCategory.cedears, base_currency="USD"),
]

_SNAPSHOTS = [
    InvestmentSnapshot(investment_id=_ARS, user_id=1, date=date(2026, 1, 10), value=Decimal("100000"), currency="ARS"),
    InvestmentSnapshot(investment_id=_ARS, user_id=1, date=date(2026, 2, 10), value=Decimal("125000"), currency="ARS"),
    InvestmentSnapshot(investment_id=_USD, user_id=1, date=date(2026, 3, 10), value=Decimal("50"), currency="USD"),
]

_TRANSACTIONS = [
    Transaction(investment_id=_ARS, user_id=1, date=date(2026, 1, 10), amount=Decimal("100000"), currency="ARS", type=TransactionType.buy),
    Transaction(investment_id=_USD, user_id=1, date=date(2026, 3, 10), amount=Decimal("50"), currency="USD", type=TransactionType.buy),
]


# The repositories answer from the fixture, filtered by the ids asked for, as the SQL would.
@pytest.fixture
def wired(monkeypatch):
    repo = metrics_service.metrics_repository

    async def snapshots(_session, ids):
        return [s for s in _SNAPSHOTS if s.investment_id in ids]

    async def transactions(_session, ids):
        return [t for t in _TRANSACTIONS if t.investment_id in ids]

    async def latest(_session, ids):
        return {s.investment_id: s for s in _SNAPSHOTS if s.investment_id in ids}

    async def by_id(_session, investment_id, _user_id):
        return next(i for i in _INVESTMENTS if i.id == investment_id)

    monkeypatch.setattr(repo, "list_active_investments", AsyncMock(return_value=list(_INVESTMENTS)))
    monkeypatch.setattr(repo, "list_snapshots_by_investments", snapshots)
    monkeypatch.setattr(repo, "list_transactions_by_investments", transactions)
    monkeypatch.setattr(repo, "get_latest_snapshots", latest)
    monkeypatch.setattr(metrics_service.investment_repository, "get_by_id", by_id)
    collections = metrics_service.collection_repository
    monkeypatch.setattr(collections, "list_by_user", AsyncMock(return_value=[InvestmentCollection(id=7, user_id=1, name="Argentina")]))
    monkeypatch.setattr(collections, "get_investment_ids_by_collections", AsyncMock(return_value={7: [_ARS]}))
    lookup = RateLookup(dollar_preference="mep", rates_by_pair=_RATES)
    monkeypatch.setattr(metrics_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))


@pytest.mark.usefixtures("wired")
class TestEveryEndpointConvertsHistoryAtItsOwnDate:
    @pytest.mark.asyncio
    async def test_investment_metrics(self):
        response = await metrics_service.get_investment_metrics(AsyncMock(), _ARS, 1, currency="USD")
        assert response.current_value == Decimal("100.00")
        assert response.invested_capital == Decimal("100.00")
        assert response.absolute_gain == Decimal("0.00")
        assert [(p.date, p.value) for p in response.period_returns] == [
            (date(2026, 1, 10), Decimal("100.00")),
            (date(2026, 2, 10), Decimal("100.00")),
        ]
        # Paid 100 USD in January, worth 100 USD in February: no money-weighted return in dollars.
        assert response.irr is not None and abs(response.irr) < 1e-6

    @pytest.mark.asyncio
    async def test_portfolio_metrics(self):
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="USD")
        assert response.total_value == Decimal("150.00")
        assert response.total_invested == Decimal("150.00")
        assert response.absolute_gain == Decimal("0.00")
        assert response.total_return_pct == Decimal("0")
        # March (150: the carried peso holding at 100 plus the new 50) against February (100).
        assert response.month_change == Decimal("50.00")
        assert response.month_change_pct == Decimal("0.5")
        assert response.twr == Decimal("0")
        assert response.irr is not None and abs(response.irr) < 1e-6

    @pytest.mark.asyncio
    async def test_portfolio_metrics_over_a_window(self):
        # February alone: the peso holding is worth 100 USD at both ends and nothing moved inside.
        response = await metrics_service.get_portfolio_metrics(
            AsyncMock(), 1, currency="USD", start_date=date(2026, 1, 31), end_date=date(2026, 2, 28)
        )
        assert response.total_value == Decimal("100.00")
        assert response.total_invested == Decimal("0")
        assert response.absolute_gain == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_portfolio_evolution(self):
        response = await metrics_service.get_portfolio_evolution(AsyncMock(), 1, currency="USD")
        # March carries February's 125,000 ARS forward, at February's rate (100), beside the new 50.
        assert [(p.date, p.total_value) for p in response.points] == [
            (date(2026, 1, 1), Decimal("100.00")),
            (date(2026, 2, 1), Decimal("100.00")),
            (date(2026, 3, 1), Decimal("150.00")),
        ]

    @pytest.mark.asyncio
    async def test_allocation(self):
        response = await metrics_service.get_allocation(AsyncMock(), 1, currency="USD")
        assert response.total_value == Decimal("150.00")
        assert {item.category: item.value for item in response.items} == {"stocks": Decimal("100.00"), "cedears": Decimal("50")}

    @pytest.mark.asyncio
    async def test_allocation_by_collection(self):
        response = await metrics_service.get_allocation_by_collection(AsyncMock(), 1, currency="USD")
        assert response.total_value == Decimal("150.00")
        assert {item.collection_name: item.value for item in response.items} == {"Argentina": Decimal("100.00"), "Unassigned": Decimal("50")}

    @pytest.mark.asyncio
    async def test_investments_summary(self):
        response = await metrics_service.get_investments_summary(AsyncMock(), 1, currency="USD")
        by_id = {item.investment_id: item for item in response.items}
        peso = by_id[_ARS]
        assert peso.current_value == Decimal("100.00")
        assert peso.invested_capital == Decimal("100.00")
        assert peso.absolute_gain == Decimal("0.00")
        assert peso.month_change_pct == Decimal("0")
        assert by_id[_USD].current_value == Decimal("50")
