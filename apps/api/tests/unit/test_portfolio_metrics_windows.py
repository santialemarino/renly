from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.investment import Investment, InvestmentCategory
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services import metrics_service
from app.utils.metrics import RateLookup

# The portfolio endpoint's headline figures, driven through the service with the repositories answering
# from a fixture — one dollar holding, so no conversion is involved and every figure is the arithmetic
# under test.


def _snap(d: date, value: str, investment_id: int = 1) -> InvestmentSnapshot:
    return InvestmentSnapshot(investment_id=investment_id, user_id=1, date=d, value=Decimal(value), currency="USD")


def _wire(monkeypatch, snapshots: list[InvestmentSnapshot], transactions: list[Transaction], today: date) -> None:
    repo = metrics_service.metrics_repository
    holdings = [
        Investment(id=inv_id, user_id=1, name=f"Holding {inv_id}", category=InvestmentCategory.cedears, base_currency="USD")
        for inv_id in sorted({s.investment_id for s in snapshots})
    ]
    monkeypatch.setattr(repo, "list_active_investments", AsyncMock(return_value=holdings))
    monkeypatch.setattr(repo, "list_snapshots_by_investments", AsyncMock(return_value=snapshots))
    monkeypatch.setattr(repo, "list_transactions_by_investments", AsyncMock(return_value=transactions))
    monkeypatch.setattr(metrics_service.settings_service, "get_user_today", AsyncMock(return_value=today))

    async def by_id(_session, investment_id, _user_id):
        return next(h for h in holdings if h.id == investment_id)

    async def snapshots_of(_session, ids):
        return [s for s in snapshots if s.investment_id in ids]

    async def transactions_of(_session, ids):
        return [t for t in transactions if t.investment_id in ids]

    monkeypatch.setattr(repo, "list_snapshots_by_investments", snapshots_of)
    monkeypatch.setattr(repo, "list_transactions_by_investments", transactions_of)
    monkeypatch.setattr(metrics_service.investment_repository, "get_by_id", by_id)


def _deposit(d: date, amount: str, kind: TransactionType = TransactionType.deposit) -> Transaction:
    return Transaction(investment_id=1, user_id=1, date=d, amount=Decimal(amount), currency="USD", type=kind)


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


# "vs last month" under the gain card is what the portfolio GAINED since the end of last month — the
# value change less the money moved in — not the change in value, which reads a deposit as gain.
class TestTheMonthChangeIsAGainNotAValueChange:
    @pytest.mark.asyncio
    async def test_a_deposit_this_month_is_not_gain(self, monkeypatch):
        # 1,000 at the end of October, 500 deposited on Nov 3, 1,530 on Nov 5: the month gained 30 on
        # 1,500 at work (2%), not the 530 (53%) the value moved.
        _wire(
            monkeypatch,
            [_snap(date(2026, 10, 20), "1000"), _snap(date(2026, 11, 5), "1530")],
            [_deposit(date(2026, 11, 3), "500")],
            date(2026, 11, 9),
        )
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.month_change == Decimal("30")
        assert portfolio.month_change_pct == Decimal("0.02")
        summary = await metrics_service.get_investments_summary(AsyncMock(), 1)
        assert summary.items[0].month_change_pct == Decimal("0.02")

    @pytest.mark.asyncio
    async def test_a_holding_first_valued_this_month_is_capital_not_gain(self, monkeypatch):
        # The 200 holding first valued on Nov 4 entered the portfolio this month: contributed capital.
        snaps = [_snap(date(2026, 10, 20), "1000"), _snap(date(2026, 11, 5), "1010"), _snap(date(2026, 11, 4), "200", investment_id=2)]
        _wire(monkeypatch, snaps, [], date(2026, 11, 9))
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.month_change == Decimal("10")
        assert portfolio.month_change_pct == Decimal("10") / Decimal("1200")

    @pytest.mark.asyncio
    async def test_money_moved_in_before_the_month_end_belongs_to_the_starting_value(self, monkeypatch):
        # 1,000 valued Oct 10, 200 deposited Oct 20 (no snapshot has seen it by Oct 31), 1,236 on Nov 5:
        # 1,200 was at work when November began, so the month gained 36 (3%).
        _wire(
            monkeypatch,
            [_snap(date(2026, 10, 10), "1000"), _snap(date(2026, 11, 5), "1236")],
            [_deposit(date(2026, 10, 20), "200")],
            date(2026, 11, 9),
        )
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.month_change == Decimal("36")
        assert portfolio.month_change_pct == Decimal("0.03")
        summary = await metrics_service.get_investments_summary(AsyncMock(), 1)
        assert summary.items[0].month_change_pct == Decimal("0.03")


# Money moved in or out after a holding's last snapshot is held from the day it moves, though no
# snapshot has valued it yet — nothing snapshots when a transaction is recorded, so until the next
# snapshot it counts at cost. Leaving it out of the end of a gain read a buy as a loss and a sell as a
# gain until then.
class TestMoneyMovedSinceTheLastSnapshotIsHeldNow:
    _SNAPS = [_snap(date(2026, 9, 2), "1000")]

    @pytest.mark.asyncio
    async def test_a_buy_after_the_last_snapshot_is_not_a_loss_this_month(self, monkeypatch):
        _wire(monkeypatch, self._SNAPS, [_deposit(date(2026, 11, 5), "1000")], date(2026, 11, 9))
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.month_change == Decimal("0")
        assert portfolio.month_change_pct == Decimal("0")
        summary = await metrics_service.get_investments_summary(AsyncMock(), 1)
        assert summary.items[0].month_change_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_a_sell_after_the_last_snapshot_is_not_a_gain_this_month(self, monkeypatch):
        _wire(monkeypatch, self._SNAPS, [_deposit(date(2026, 11, 5), "300", TransactionType.sell)], date(2026, 11, 9))
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.month_change == Decimal("0")
        summary = await metrics_service.get_investments_summary(AsyncMock(), 1)
        assert summary.items[0].month_change_pct == Decimal("0")

    @pytest.mark.asyncio
    async def test_a_window_still_open_ends_with_the_money_moved_in_since(self, monkeypatch):
        # 1,000 on Dec 15, 1,100 on Feb 1, 500 deposited Mar 5, today Mar 10. The year gained 100 (and
        # its TWR is 10%), not the −400 an end that ignored the deposit read.
        snaps = [_snap(date(2025, 12, 15), "1000"), _snap(date(2026, 2, 1), "1100")]
        _wire(monkeypatch, snaps, [_deposit(date(2026, 3, 5), "500")], date(2026, 3, 10))
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, start_date=date(2026, 1, 1))
        assert response.absolute_gain == Decimal("100")
        assert response.twr == Decimal("0.1")
        # The money-weighted return closes on the same value, so it is a gain too.
        assert response.irr is not None and response.irr > 0


# With no money moving in a window, the TWR and the window's simple return answer the same question —
# how much did what was held at the start grow — so they must agree. It holds only when every point of
# the TWR's chain values what was held at that point's own rate, and the chain closes on the same value
# the gain ends at: a dollar holding viewed in pesos, carried across months whose rates move, with the
# window still open today, a month after its last snapshot.
class TestTheTwrAndThePeriodReturnAgreeWithoutFlows:
    _RATES = {
        ExchangeRatePair.USD_ARS_MEP: [
            ExchangeRate(date=date(2025, 12, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1000"), source="test"),
            ExchangeRate(date=date(2026, 1, 20), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1100"), source="test"),
            ExchangeRate(date=date(2026, 2, 20), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1250"), source="test"),
            ExchangeRate(date=date(2026, 3, 25), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal("1400"), source="test"),
        ],
    }

    @pytest.mark.asyncio
    @pytest.mark.parametrize("start", [date(2026, 1, 1), date(2026, 1, 10), date(2026, 2, 1)])
    async def test_in_pesos_for_a_dollar_holding(self, monkeypatch, start):
        snaps = [_snap(date(2025, 12, 10), "100"), _snap(date(2026, 1, 10), "104"), _snap(date(2026, 2, 10), "103"), _snap(date(2026, 3, 1), "110")]
        _wire(monkeypatch, snaps, [], date(2026, 4, 5))
        lookup = RateLookup(dollar_preference="mep", rates_by_pair=self._RATES)
        monkeypatch.setattr(metrics_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))
        response = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="ARS", start_date=start)
        assert response.total_return_pct is not None and response.twr is not None
        assert abs(response.twr - response.total_return_pct) < Decimal("1e-20")


# Without a window the portfolio is a window opening before its first snapshot and still open today, so
# its IRR is that window's — closing TODAY on the value the gain ends at, not on each holding's own last
# snapshot. The fixture's two holdings were last valued months apart, and the dollar one is viewed in
# pesos while the rate moves after its last snapshot.
class TestTheAllTimeFiguresCloseToday:
    _RATES = TestTheTwrAndThePeriodReturnAgreeWithoutFlows._RATES

    def _wire(self, monkeypatch):
        snaps = [
            _snap(date(2025, 12, 10), "100"),
            _snap(date(2026, 1, 10), "104"),
            _snap(date(2026, 1, 5), "50", investment_id=2),
            _snap(date(2026, 2, 10), "58", investment_id=2),
        ]
        _wire(monkeypatch, snaps, [_deposit(date(2026, 3, 20), "40")], date(2026, 4, 5))
        lookup = RateLookup(dollar_preference="mep", rates_by_pair=self._RATES)
        monkeypatch.setattr(metrics_service.exchange_rate_service, "get_user_rate_lookup", AsyncMock(return_value=lookup))

    @pytest.mark.asyncio
    async def test_the_all_time_irr_is_the_open_windows_from_before_the_first_snapshot(self, monkeypatch):
        self._wire(monkeypatch)
        all_time = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="ARS")
        window = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="ARS", start_date=date(2025, 12, 1))
        assert all_time.irr is not None
        assert all_time.irr == window.irr

    @pytest.mark.asyncio
    async def test_a_single_holdings_irr_is_the_portfolios(self, monkeypatch):
        self._wire(monkeypatch)
        detail = await metrics_service.get_investment_metrics(AsyncMock(), 1, 1, currency="ARS")
        alone = await metrics_service.get_portfolio_metrics(AsyncMock(), 1, currency="ARS", investment_ids=[1])
        assert detail.irr is not None
        assert detail.irr == alone.irr

    @pytest.mark.asyncio
    async def test_the_all_time_gain_counts_a_buy_not_yet_snapshotted_at_cost(self, monkeypatch):
        # Holding 1: 100 opening, 104 last valued, 40 bought on Mar 20 after that. Its gain is 4, not −36,
        # and the portfolio's adds holding 2's 8; the value stays what the snapshots say.
        self._wire(monkeypatch)
        portfolio = await metrics_service.get_portfolio_metrics(AsyncMock(), 1)
        assert portfolio.total_value == Decimal("162")
        assert portfolio.total_invested == Decimal("190")
        assert portfolio.absolute_gain == Decimal("12")
        summary = {i.investment_id: i for i in (await metrics_service.get_investments_summary(AsyncMock(), 1)).items}
        assert summary[1].absolute_gain == Decimal("4")
        detail = await metrics_service.get_investment_metrics(AsyncMock(), 1, 1)
        assert detail.absolute_gain == Decimal("4")
        assert detail.simple_return is not None and abs(detail.simple_return - Decimal("4") / Decimal("140")) < Decimal("1e-20")
