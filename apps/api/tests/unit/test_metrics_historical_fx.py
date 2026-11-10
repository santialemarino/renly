from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.account import Account, AccountType
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.investment import Investment, InvestmentCategory
from app.models.investment_collection import InvestmentCollection
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services import dashboard_service, metrics_service
from app.utils.metrics import RateLookup

# One rule, two halves, pinned on every investment endpoint because each walks its own rows:
#
#   * HISTORY converts at the rate in force on its own date — a transaction at its date, a period-return
#     point at its snapshot's date, a point of the evolution chart at ITS month's rate (a holding carried
#     forward from an older snapshot included), a window's start at the start's rate. Restating the past
#     at today's rate would invent a gain or a loss that never happened at the time.
#   * What is HELD NOW converts at TODAY's rate — the headline value, the allocation donuts, every
#     per-holding current value — exactly as cash and card balances do, so a holding and the same amount
#     of cash read the same. The gain (value now minus the capital put in at its own dates) therefore
#     includes the currency's move since, which is intended: it is what the holding gained in the display
#     currency.
#
# The fixture is built so the answers cannot coincide. The peso holding is worth exactly 100 USD at every
# snapshot (100,000 ARS at 1,000 in January, 125,000 ARS at 1,250 in February), and the last stored rate —
# the one "today" (March 20) resolves to — is 2,000, so NOW it is worth 62.50 USD. A dollar holding first
# valued in March sits beside it, so the evolution chart has a month in which the peso holding is CARRIED
# FORWARD and must convert at March's rate, as the headline does.

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

_TODAY = date(2026, 3, 20)

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
    monkeypatch.setattr(metrics_service.settings_service, "get_user_today", AsyncMock(return_value=_TODAY))
    return lookup


@pytest.mark.usefixtures("wired")
class TestHistoryAtItsOwnDateHoldingsAtTodaysRate:
    @pytest.mark.asyncio
    async def test_investment_metrics(self):
        response = await metrics_service.get_investment_metrics(AsyncMock(), _ARS, 1, currency="USD")
        # Held now: 125,000 ARS at today's 2,000. Paid in: 100,000 ARS at January's 1,000.
        assert response.current_value == Decimal("62.50")
        assert response.invested_capital == Decimal("100.00")
        assert response.absolute_gain == Decimal("-37.50")
        assert [(p.date, p.value) for p in response.period_returns] == [
            (date(2026, 1, 10), Decimal("100.00")),
            (date(2026, 2, 10), Decimal("100.00")),
        ]
        # The IRR's flows convert at their own dates and it closes TODAY on the value now: paid 100 USD
        # in January, worth 62.50 USD on March 20 — a money-weighted loss, like the gain above.
        assert response.irr is not None and response.irr < 0

    @pytest.mark.asyncio
    async def test_portfolio_metrics(self):
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="USD")
        # Now: 62.50 (the peso holding at today's rate) + 50. In: 100 + 50, each at its own date.
        assert response.total_value == Decimal("112.50")
        assert response.total_invested == Decimal("150.00")
        assert response.absolute_gain == Decimal("-37.50")
        assert response.total_return_pct == Decimal("-0.25")
        # The gain into today: 112.50 now against the end of February, when only the peso holding was
        # held — 125,000 ARS at February's 1,250, so 100 — less the 50 the dollar holding brought in
        # this month (its first snapshot is contributed capital, not gain), over the 150 at work.
        assert response.month_change == Decimal("-37.50")
        assert response.month_change_pct == Decimal("-0.25")
        # The TWR chains points that each value what was held then at that point's rate, and runs to
        # today: the peso holding is 100 USD at both February points, then 62.50 once March's rate
        # applies to it — a 37.5% fall the gain above shows too. (The dollar holding's 50 is capital.)
        assert response.twr == Decimal("-0.375")
        # The IRR closes on the same value today, so it is a loss too.
        assert response.irr is not None and response.irr < 0

    @pytest.mark.asyncio
    async def test_portfolio_metrics_over_a_past_window(self):
        # February alone, a window that closed in the past: each boundary values what was held then at
        # that day's rate — 100,000 ARS at 1,000 on Jan 31, 125,000 ARS at 1,250 on Feb 28 — so both
        # are 100 USD, and nothing moved inside.
        response = await metrics_service.get_portfolio_metrics(
            AsyncMock(), 1, currency="USD", start_date=date(2026, 1, 31), end_date=date(2026, 2, 28)
        )
        assert response.total_value == Decimal("100.00")
        assert response.total_invested == Decimal("0")
        assert response.absolute_gain == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_portfolio_metrics_over_a_window_still_open(self):
        # From Jan 31 to today: the end is NOW, so it is the headline's 112.50; the start is 100 at Jan
        # 31's rate; 50 went in inside the window (the dollar holding's first snapshot).
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="USD", start_date=date(2026, 1, 31))
        assert response.total_value == Decimal("112.50")
        assert response.total_invested == Decimal("50")
        assert response.absolute_gain == Decimal("-37.50")

    @pytest.mark.asyncio
    async def test_portfolio_evolution(self):
        response = await metrics_service.get_portfolio_evolution(AsyncMock(), 1, currency="USD")
        # March carries February's 125,000 ARS forward and values it at MARCH's rate (62.50), beside the
        # new 50 — the same 112.50 the headline reads.
        assert [(p.date, p.total_value) for p in response.points] == [
            (date(2026, 1, 1), Decimal("100.00")),
            (date(2026, 2, 1), Decimal("100.00")),
            (date(2026, 3, 1), Decimal("112.50")),
        ]

    @pytest.mark.asyncio
    async def test_allocation(self):
        response = await metrics_service.get_allocation(AsyncMock(), 1, currency="USD")
        assert response.total_value == Decimal("112.50")
        assert {item.category: item.value for item in response.items} == {"stocks": Decimal("62.50"), "cedears": Decimal("50")}

    @pytest.mark.asyncio
    async def test_allocation_by_collection(self):
        response = await metrics_service.get_allocation_by_collection(AsyncMock(), 1, currency="USD")
        assert response.total_value == Decimal("112.50")
        assert {item.collection_name: item.value for item in response.items} == {"Argentina": Decimal("62.50"), "Unassigned": Decimal("50")}

    @pytest.mark.asyncio
    async def test_investments_summary(self):
        response = await metrics_service.get_investments_summary(AsyncMock(), 1, currency="USD")
        by_id = {item.investment_id: item for item in response.items}
        peso = by_id[_ARS]
        assert peso.current_value == Decimal("62.50")
        assert peso.invested_capital == Decimal("100.00")
        assert peso.absolute_gain == Decimal("-37.50")
        # 62.50 now against 100 at the end of February.
        assert peso.month_change_pct == Decimal("-0.375")
        assert by_id[_USD].current_value == Decimal("50")


# The invariants the rule exists to keep, each across two surfaces that used to disagree.
class TestTheRuleHoldsAcrossSurfaces:
    @pytest.mark.asyncio
    async def test_a_holding_and_the_same_cash_convert_identically_today(self, wired):
        # 125,000 ARS held as an investment and 125,000 ARS held in an account are the same money. The
        # cash total converts at today's rate; so must the holding, or 3,000 USD reads one figure as a
        # holding and another as cash.
        account = Account(id=9, user_id=1, name="Caja", type=AccountType.bank, currency="ARS", opening_date=date(2026, 1, 1))
        cash, skipped = dashboard_service.compute_cash_total([account], {9: Decimal("125000")}, "USD", wired.get_rate_map_at(_TODAY))
        holding = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="USD", investment_ids=[_ARS])
        assert skipped == set()
        assert holding.total_value == cash == Decimal("62.50")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("today", [_TODAY, date(2026, 5, 6)])
    async def test_the_charts_last_point_is_todays_headline(self, wired, monkeypatch, today):
        # Also from a later month than any snapshot (May): the chart runs on to the current month, and
        # its last point carries every holding forward at today's rate — the headline's own figure.
        monkeypatch.setattr(metrics_service.settings_service, "get_user_today", AsyncMock(return_value=today))
        evolution = await metrics_service.get_portfolio_evolution(AsyncMock(), 1, currency="USD")
        headline = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="USD")
        assert evolution.points[-1].date == date(today.year, today.month, 1)
        assert evolution.points[-1].total_value == headline.total_value


# An investment can sit in several collections. Each collection's share is of the PORTFOLIO — every
# investment counted once — so a target compares against what is really there. Summing the buckets as
# the base counted the shared investment once per collection and shrank every share.
@pytest.mark.usefixtures("wired")
class TestOverlappingCollections:
    @pytest.mark.asyncio
    async def test_shares_are_of_the_portfolio_counted_once(self, monkeypatch):
        collections = metrics_service.collection_repository
        monkeypatch.setattr(
            collections,
            "list_by_user",
            AsyncMock(
                return_value=[
                    InvestmentCollection(id=7, user_id=1, name="Argentina", target_percentage=Decimal("50")),
                    InvestmentCollection(id=8, user_id=1, name="Everything", target_percentage=Decimal("100")),
                ]
            ),
        )
        monkeypatch.setattr(collections, "get_investment_ids_by_collections", AsyncMock(return_value={7: [_ARS], 8: [_ARS, _USD]}))
        response = await metrics_service.get_allocation_by_collection(AsyncMock(), 1, currency="USD")
        allocation = await metrics_service.get_allocation(AsyncMock(), 1, currency="USD")
        # 62.50 + 50 = 112.50 held; the peso holding is in both collections but in the portfolio once.
        assert response.total_value == allocation.total_value == Decimal("112.50")
        by_name = {item.collection_name: item for item in response.items}
        assert by_name["Everything"].percentage == Decimal("100")
        assert by_name["Everything"].difference == Decimal("0")
        assert by_name["Argentina"].percentage == Decimal("62.50") / Decimal("112.50") * 100
