from datetime import date as date_type
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.domain import CardBucketBalance
from app.models.account import Account, AccountType
from app.models.credit_card import CreditCard
from app.models.group import Group, GroupKind
from app.models.investment import InvestmentCategory
from app.schemas.finance_metrics import FinanceOverviewResponse
from app.schemas.metrics import (
    AllocationItem,
    AllocationResponse,
    EvolutionPoint,
    PortfolioEvolutionResponse,
    PortfolioMetricsResponse,
    SkippedInvestment,
)
from app.services import dashboard_service, exchange_rate_service, settings_service, shared_worth_service
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
# Every dashboard read now consults the shared side. The tests below are about the private half, so
# the context comes back empty — which is also the only state a solo user is ever in, and both shared
# functions short-circuit on it without issuing a single query.
def _no_shared(monkeypatch) -> None:
    monkeypatch.setattr(
        dashboard_service.shared_worth_service,
        "load_context",
        AsyncMock(return_value=shared_worth_service.SharedContext(seats=[], pots=[], positions=[])),
    )


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
        _no_shared(monkeypatch)

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
        _no_shared(monkeypatch)

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

    def test_negative_balance_reduces_total(self):
        accounts = [_acct(1, "ARS"), _acct(2, "USD")]
        # −500 ARS + (−10 USD → −12,000 ARS) = −12,500 ARS. An overdraft reduces the cash total (and
        # thus net worth); a negative balance is a real signed value, never flagged skipped.
        total, skipped = compute_cash_total(accounts, {1: Decimal("-500"), 2: Decimal("-10")}, "ARS", RATE_MAP)
        assert total == Decimal("-12500")
        assert skipped == set()


class TestComputeMonthlyCashBalances:
    # The series takes BALANCES now, one per month per account, straight from the eleven-source engine
    # the headline reads — so these tests are about conversion and reporting, not about which movements
    # count. Which movements count is compute_account_balance_series' own subject, and having only one
    # answer to it is the point of the change.
    def test_each_month_sums_every_accounts_balance(self):
        accounts = [_acct(1, "ARS"), _acct(2, "ARS")]
        balances = {1: [Decimal("1000"), Decimal("1500")], 2: [Decimal("200"), Decimal("0")]}
        month_ends = [date_type(2026, 1, 31), date_type(2026, 2, 28)]
        result, skipped = compute_monthly_cash_balances(accounts, balances, month_ends, None, None)
        assert result == [Decimal("1200"), Decimal("1500")]
        assert skipped == []

    def test_each_month_converts_at_ITS_OWN_rate(self):
        # The behaviour this rewrite changed, and the reason for it: a foreign-currency balance now
        # tracks its own currency over time instead of staying frozen at the rate of the month the
        # money arrived. Same 100 USD in both months, a rate that halves — so the ARS figure halves.
        class _MovingLookup:
            def get_rate_map_at(self, as_of_date: date_type) -> dict[str, Decimal]:
                ars = Decimal("1000") if as_of_date.month == 1 else Decimal("500")
                return {"USD": Decimal("1"), "ARS": ars}

        accounts = [_acct(1, "USD")]
        balances = {1: [Decimal("100"), Decimal("100")]}
        month_ends = [date_type(2026, 1, 31), date_type(2026, 2, 28)]
        result, skipped = compute_monthly_cash_balances(accounts, balances, month_ends, "ARS", _MovingLookup())
        assert result == [Decimal("100000"), Decimal("50000")]
        assert skipped == []

    def test_unconvertible_currency_is_dropped_and_reported(self):
        # EUR can't reach ARS via RATE_MAP, so it is dropped from the series AND its code is flagged
        # (fail-loud, like the card equivalent); the ARS account still contributes.
        accounts = [_acct(1, "ARS"), _acct(2, "EUR")]
        balances = {1: [Decimal("1000")], 2: [Decimal("50")]}
        result, skipped = compute_monthly_cash_balances(accounts, balances, [date_type(2026, 1, 31)], "ARS", FIXED_LOOKUP)
        assert result == [Decimal("1000")]
        assert skipped == ["EUR"]

    def test_a_zero_balance_never_flags_its_currency(self):
        # Mirrors compute_cash_total: a zero contributes nothing either way, so reporting its currency
        # as skipped would make the two totals disagree about what they dropped.
        accounts = [_acct(1, "ARS"), _acct(2, "EUR")]
        balances = {1: [Decimal("1000")], 2: [Decimal("0")]}
        result, skipped = compute_monthly_cash_balances(accounts, balances, [date_type(2026, 1, 31)], "ARS", FIXED_LOOKUP)
        assert result == [Decimal("1000")]
        assert skipped == []


class TestTheEvolutionGrid:
    # The grid is the union of every term's history, which is what makes a chart exist at all for a
    # user who holds no investments — the case the old portfolio-only grid returned nothing for.
    def _grid(self, **kwargs) -> list[tuple[int, int]]:
        defaults = dict(portfolio_months=[], card_months=[], accounts=[], shared_start=None, today=None, date_from=None, date_to=None)
        return dashboard_service._evolution_grid(**{**defaults, **kwargs})

    def test_an_account_alone_produces_a_grid(self):
        # The pre-existing defect: a cash-only user got no chart, because the months came from the
        # investment side and the cash side was only ever read onto them.
        assert self._grid(accounts=[_acct(1, "ARS", opening_date=date_type(2026, 5, 3))], today=date_type(2026, 7, 15)) == [
            (2026, 5),
            (2026, 6),
            (2026, 7),
        ]

    def test_a_shared_side_alone_produces_a_grid(self):
        assert self._grid(shared_start=(2026, 6), today=date_type(2026, 7, 2)) == [(2026, 6), (2026, 7)]

    def test_it_starts_at_the_EARLIEST_term_not_the_investment_one(self):
        grid = self._grid(
            portfolio_months=[(2026, 6)],
            accounts=[_acct(1, "ARS", opening_date=date_type(2026, 3, 20))],
            shared_start=(2026, 4),
            today=date_type(2026, 6, 10),
        )
        assert grid[0] == (2026, 3)

    def test_it_runs_to_the_current_month_past_the_last_snapshot(self):
        assert self._grid(portfolio_months=[(2026, 6)], today=date_type(2026, 8, 1))[-1] == (2026, 8)

    def test_the_window_clips_BOTH_ends(self):
        # Clipping the end is the fix for a window that closed in June gaining a September point,
        # which appending "today" unconditionally used to do.
        grid = self._grid(
            portfolio_months=[(2026, 1), (2026, 12)],
            today=date_type(2026, 9, 30),
            date_from=date_type(2026, 4, 15),
            date_to=date_type(2026, 6, 30),
        )
        assert grid == [(2026, 4), (2026, 5), (2026, 6)]

    def test_nothing_at_all_is_an_empty_grid(self):
        assert self._grid(today=date_type(2026, 7, 1)) == []

    def test_a_window_that_ends_before_it_starts_is_empty(self):
        assert self._grid(portfolio_months=[(2026, 6)], date_from=date_type(2026, 8, 1)) == []


class TestNetWorthEvolutionCurrentMonth:
    # The series extends to the current month (forward-filling investments), so cash/card activity
    # that post-dates the latest investment snapshot still advances net worth (and the MoM delta).
    @pytest.mark.asyncio
    async def test_appends_current_month_with_cash_beyond_last_snapshot(self, monkeypatch):
        evo = PortfolioEvolutionResponse(points=[EvolutionPoint(date=date_type(2026, 6, 1), total_value=Decimal("5000"))])
        monkeypatch.setattr(dashboard_service.metrics_service, "get_portfolio_evolution", AsyncMock(return_value=evo))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            dashboard_service.account_repository,
            "list_by_user",
            AsyncMock(return_value=[_acct(1, "ARS", opening="1000", opening_date=date_type(2026, 7, 1))]),
        )
        monkeypatch.setattr(
            dashboard_service.account_service,
            "compute_account_balance_series",
            AsyncMock(return_value={1: [Decimal("0"), Decimal("1000")]}),
        )
        _no_shared(monkeypatch)

        points, _ = await dashboard_service.compute_net_worth_evolution(AsyncMock(), 1, currency=None, lookup=None, today=date_type(2026, 7, 15))

        # A July point is appended: investment forward-filled from June (5000), cash 1000 → net worth 6000.
        assert [(p.date, p.cash_balance, p.net_worth) for p in points] == [
            (date_type(2026, 6, 1), Decimal("0"), Decimal("5000")),
            (date_type(2026, 7, 1), Decimal("1000"), Decimal("6000")),
        ]

    @pytest.mark.asyncio
    async def test_no_current_month_appended_when_snapshot_is_already_current(self, monkeypatch):
        evo = PortfolioEvolutionResponse(points=[EvolutionPoint(date=date_type(2026, 7, 1), total_value=Decimal("5000"))])
        monkeypatch.setattr(dashboard_service.metrics_service, "get_portfolio_evolution", AsyncMock(return_value=evo))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=[]))
        _no_shared(monkeypatch)

        points, _ = await dashboard_service.compute_net_worth_evolution(AsyncMock(), 1, currency=None, lookup=None, today=date_type(2026, 7, 15))

        assert [p.date for p in points] == [date_type(2026, 7, 1)]


def _zero_finance_overview() -> FinanceOverviewResponse:
    return FinanceOverviewResponse(
        total_income=Decimal("0"),
        total_expenses=Decimal("0"),
        net=Decimal("0"),
        credit_card_balance=Decimal("0"),
    )


class TestTheYoursSharedSplit:
    # X1 in one class: the headline answers "what am I worth", Yours and Shared decompose it exactly,
    # and every asset card counts the same universe the composition donut does.
    def _patch(self, monkeypatch, *, shared: shared_worth_service.SharedWorth, investments="0", cash="0", card="0") -> None:
        monkeypatch.setattr(
            dashboard_service.metrics_service,
            "get_portfolio_metrics",
            AsyncMock(
                return_value=PortfolioMetricsResponse(total_value=Decimal(investments), total_invested=Decimal("0"), absolute_gain=Decimal("0"))
            ),
        )
        finance = _zero_finance_overview()
        finance.credit_card_balance = Decimal(card)
        monkeypatch.setattr(dashboard_service.finance_metrics_service, "get_overview", AsyncMock(return_value=finance))
        accounts = [_acct(1, "ARS", opening=cash)]
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=accounts))
        monkeypatch.setattr(dashboard_service.account_service, "get_account_balances", AsyncMock(return_value={1: Decimal(cash)}))
        monkeypatch.setattr(dashboard_service, "compute_net_worth_evolution", AsyncMock(return_value=([], [])))
        monkeypatch.setattr(
            dashboard_service.shared_worth_service,
            "load_context",
            AsyncMock(return_value=shared_worth_service.SharedContext(seats=[], pots=[], positions=[])),
        )
        monkeypatch.setattr(dashboard_service.shared_worth_service, "get_shared_worth", AsyncMock(return_value=shared))

    @pytest.mark.asyncio
    async def test_yours_plus_shared_is_the_headline(self, monkeypatch):
        shared = shared_worth_service.SharedWorth(
            pot_value=Decimal("400"),
            receivable=Decimal("50"),
            payable=Decimal("20"),
            buckets={"cash": Decimal("150"), "fci": Decimal("250")},
            has_shared=True,
        )
        self._patch(monkeypatch, shared=shared, investments="1000", cash="300", card="100")
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        # Yours = 1000 + 300 − 100; Shared = 400 + 50 − 20.
        assert result.private_net_worth == Decimal("1200")
        assert result.shared_net_worth == Decimal("430")
        assert result.net_worth == Decimal("1630")
        assert result.private_net_worth + result.shared_net_worth == result.net_worth

    @pytest.mark.asyncio
    async def test_the_cash_and_investment_cards_count_the_shared_share_too(self, monkeypatch):
        # Decided rather than assumed: if the donut folds a jointly-held bank account into `cash`, the
        # Cash card above it must count the same money or the page shows two different cash figures.
        shared = shared_worth_service.SharedWorth(
            pot_value=Decimal("400"),
            buckets={"cash": Decimal("150"), "fci": Decimal("250")},
            has_shared=True,
        )
        self._patch(monkeypatch, shared=shared, investments="1000", cash="300")
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.cash_total == Decimal("450")
        assert result.investment_total == Decimal("1250")

    @pytest.mark.asyncio
    async def test_a_solo_user_reports_no_shared_side_at_all(self, monkeypatch):
        self._patch(monkeypatch, shared=shared_worth_service.SharedWorth(), investments="1000", cash="300", card="100")
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_shared is False
        assert result.shared_net_worth == Decimal("0")
        assert result.net_worth == result.private_net_worth == Decimal("1200")
        assert result.undivided_pots == []

    @pytest.mark.asyncio
    async def test_an_undivided_pot_is_named_with_its_group(self, monkeypatch):
        shared = shared_worth_service.SharedWorth(
            undivided_pots=[shared_worth_service.UndividedPot(pot_id=5, name=None, group_id=10)],
            has_shared=True,
        )
        self._patch(monkeypatch, shared=shared)
        monkeypatch.setattr(
            dashboard_service.group_repository,
            "get_by_ids",
            AsyncMock(return_value=[Group(id=10, name="Casa", kind=GroupKind.household, created_by=1)]),
        )
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert [(p.pot_id, p.name, p.group_name) for p in result.undivided_pots] == [(5, None, "Casa")]

    @pytest.mark.asyncio
    async def test_holding_only_a_shared_side_still_counts_as_holding_something(self, monkeypatch):
        # has_holdings gates the dashboard's teaching hint. A user whose only money is co-owned holds
        # plenty, and treating them as empty would offer them a first-run nudge.
        self._patch(monkeypatch, shared=shared_worth_service.SharedWorth(has_shared=True))
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(dashboard_service.account_service, "get_account_balances", AsyncMock(return_value={}))
        exists = AsyncMock(return_value=False)
        monkeypatch.setattr(dashboard_service.investment_repository, "exists_active_by_user", exists)
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_holdings is True
        exists.assert_not_called()


class TestCompositionFoldsTheSharedShare:
    def _patch(self, monkeypatch, *, shared: shared_worth_service.SharedWorth, cash: str = "0") -> None:
        monkeypatch.setattr(dashboard_service.metrics_service, "get_allocation", AsyncMock(return_value=_allocation()))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "list_by_user", AsyncMock(return_value=[]))
        accounts = [_acct(1, "ARS", opening=cash)] if cash != "0" else []
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=accounts))
        monkeypatch.setattr(dashboard_service.account_service, "get_account_balances", AsyncMock(return_value={1: Decimal(cash)}))
        monkeypatch.setattr(
            dashboard_service.shared_worth_service,
            "load_context",
            AsyncMock(return_value=shared_worth_service.SharedContext(seats=[], pots=[], positions=[])),
        )
        monkeypatch.setattr(dashboard_service.shared_worth_service, "get_shared_worth", AsyncMock(return_value=shared))

    @pytest.mark.asyncio
    async def test_a_shared_holding_lands_in_the_slice_its_kind_belongs_to(self, monkeypatch):
        # Not a "Shared" wedge: scope is not an asset class, and the Yours/Shared split is the
        # headline's job. CAT_A gains its share of the pot and the total grows by exactly that.
        shared = shared_worth_service.SharedWorth(pot_value=Decimal("200"), buckets={CAT_A: Decimal("200")}, has_shared=True)
        self._patch(monkeypatch, shared=shared)
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert dict((i.label, i.value) for i in result.items) == {CAT_A: Decimal("800"), CAT_B: Decimal("400")}
        assert result.total_assets == Decimal("1200")

    @pytest.mark.asyncio
    async def test_a_category_that_exists_only_because_of_a_shared_holding_still_gets_a_slice(self, monkeypatch):
        shared = shared_worth_service.SharedWorth(pot_value=Decimal("500"), buckets={"real_estate": Decimal("500")}, has_shared=True)
        self._patch(monkeypatch, shared=shared)
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert [i.label for i in result.items] == [CAT_A, CAT_B, "real_estate"]

    @pytest.mark.asyncio
    async def test_a_shared_bank_account_joins_the_cash_slice(self, monkeypatch):
        shared = shared_worth_service.SharedWorth(pot_value=Decimal("300"), buckets={"cash": Decimal("300")}, has_shared=True)
        self._patch(monkeypatch, shared=shared, cash="700")
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert [(i.label, i.value) for i in result.items if i.label == "cash"] == [("cash", Decimal("1000"))]

    @pytest.mark.asyncio
    async def test_a_receivable_is_its_own_asset_slice_and_a_payable_joins_liabilities(self, monkeypatch):
        # D3, on the donut: neither is ever blended into cash, and they sit on opposite sides.
        shared = shared_worth_service.SharedWorth(receivable=Decimal("250"), payable=Decimal("100"), has_shared=True)
        self._patch(monkeypatch, shared=shared)
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert [(i.label, i.value) for i in result.items if i.label in ("receivable", "liabilities")] == [
            ("receivable", Decimal("250")),
            ("liabilities", Decimal("100")),
        ]
        assert result.total_assets == Decimal("1250")
        assert result.total_liabilities == Decimal("100")

    @pytest.mark.asyncio
    async def test_the_percentages_still_sum_over_the_items_actually_shown(self, monkeypatch):
        shared = shared_worth_service.SharedWorth(receivable=Decimal("100"), has_shared=True)
        self._patch(monkeypatch, shared=shared)
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert sum(i.percentage for i in result.items) == Decimal("100")

    @pytest.mark.asyncio
    async def test_a_currency_the_shared_side_could_not_restate_is_reported(self, monkeypatch):
        shared = shared_worth_service.SharedWorth(has_shared=True, skipped_currencies={"BRL"})
        self._patch(monkeypatch, shared=shared)
        result = await dashboard_service.get_composition(AsyncMock(), 1)
        assert result.skipped_currencies == ["BRL"]


class TestTheEvolutionSeriesTerms:
    # Two terms of a point that no other test reaches, both of which a mutation sweep found could be
    # deleted with the whole suite still green.
    def _wire(self, monkeypatch, *, shared_values, card_expenses=(), shared_card=(), cards=()):
        evo = PortfolioEvolutionResponse(points=[EvolutionPoint(date=date_type(2026, 7, 1), total_value=Decimal("1000"))])
        monkeypatch.setattr(dashboard_service.metrics_service, "get_portfolio_evolution", AsyncMock(return_value=evo))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "list_by_user", AsyncMock(return_value=list(cards)))
        monkeypatch.setattr(dashboard_service.expense_repository, "sum_by_credit_card_ids_monthly", AsyncMock(return_value=list(card_expenses)))
        shared_monthly = AsyncMock(return_value=list(shared_card))
        monkeypatch.setattr(dashboard_service.shared_expense_repository, "sum_by_credit_card_ids_monthly", shared_monthly)
        monkeypatch.setattr(dashboard_service.card_settlement_repository, "sum_by_card_ids_monthly", AsyncMock(return_value=[]))
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            dashboard_service.shared_worth_service,
            "load_context",
            AsyncMock(return_value=shared_worth_service.SharedContext(seats=[], pots=[], positions=[])),
        )
        monkeypatch.setattr(
            dashboard_service.shared_worth_service,
            "get_shared_series",
            AsyncMock(return_value=(list(shared_values), set())),
        )
        return shared_monthly

    @pytest.mark.asyncio
    async def test_the_shared_half_reaches_each_points_net_worth(self, monkeypatch):
        self._wire(monkeypatch, shared_values=[Decimal("250")])
        points, _ = await dashboard_service.compute_net_worth_evolution(AsyncMock(), 1, currency=None, lookup=None, today=date_type(2026, 7, 15))
        assert [(p.private_net_worth, p.shared_value, p.net_worth) for p in points] == [(Decimal("1000"), Decimal("250"), Decimal("1250"))]

    @pytest.mark.asyncio
    async def test_a_groups_card_charge_is_in_the_monthly_card_series_too(self, monkeypatch):
        # The defect this closes: get_card_balances merges a group's charges into the CURRENT card
        # figure while the monthly series read only the private table, so the headline and the chart's
        # card line described different debts.
        card = CreditCard(id=1, user_id=1, name="Visa", closing_day=20, due_day=5, currency="ARS", is_active=True)
        self._wire(
            monkeypatch,
            shared_values=[Decimal("0")],
            cards=[card],
            card_expenses=[(1, 2026, 7, "ARS", 100.0)],
            shared_card=[(1, 2026, 7, "ARS", 400.0)],
        )
        points, _ = await dashboard_service.compute_net_worth_evolution(AsyncMock(), 1, currency=None, lookup=None, today=date_type(2026, 7, 15))
        assert [p.card_balance for p in points] == [Decimal("500")]

    @pytest.mark.asyncio
    async def test_the_shared_card_read_is_skipped_when_there_are_no_cards(self, monkeypatch):
        shared_monthly = self._wire(monkeypatch, shared_values=[Decimal("0")])
        await dashboard_service.compute_net_worth_evolution(AsyncMock(), 1, currency=None, lookup=None, today=date_type(2026, 7, 15))
        shared_monthly.assert_not_awaited()


class TestHasHoldings:
    # Patches the overview's collaborators so only the three existence signals vary. Every money
    # figure is zero, which is the whole point: has_holdings must not be a disguised value test.
    def _patch(self, monkeypatch, *, accounts: list, investments: bool, cards: bool) -> None:
        monkeypatch.setattr(
            dashboard_service.metrics_service,
            "get_portfolio_metrics",
            AsyncMock(return_value=PortfolioMetricsResponse(total_value=Decimal("0"), total_invested=Decimal("0"), absolute_gain=Decimal("0"))),
        )
        monkeypatch.setattr(
            dashboard_service.finance_metrics_service,
            "get_overview",
            AsyncMock(return_value=_zero_finance_overview()),
        )
        monkeypatch.setattr(dashboard_service.account_repository, "list_by_user", AsyncMock(return_value=accounts))
        monkeypatch.setattr(
            dashboard_service.account_service,
            "get_account_balances",
            AsyncMock(return_value={a.id: a.opening_balance for a in accounts}),
        )
        monkeypatch.setattr(dashboard_service.investment_repository, "exists_active_by_user", AsyncMock(return_value=investments))
        monkeypatch.setattr(dashboard_service.credit_card_repository, "exists_by_user", AsyncMock(return_value=cards))
        monkeypatch.setattr(dashboard_service, "compute_net_worth_evolution", AsyncMock(return_value=([], [])))
        _no_shared(monkeypatch)

    @pytest.mark.asyncio
    async def test_false_when_the_user_holds_nothing(self, monkeypatch):
        self._patch(monkeypatch, accounts=[], investments=False, cards=False)
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_holdings is False

    @pytest.mark.asyncio
    async def test_true_for_a_zero_balance_account(self, monkeypatch):
        # The regression this flag exists for: a new account's opening balance defaults to zero, so a
        # "net worth != 0" gate would call this user empty while /accounts offers them Reconcile.
        self._patch(monkeypatch, accounts=[_acct(1, "ARS", opening="0")], investments=False, cards=False)
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_holdings is True
        assert result.net_worth == Decimal("0")

    @pytest.mark.asyncio
    async def test_true_for_investments_alone(self, monkeypatch):
        self._patch(monkeypatch, accounts=[], investments=True, cards=False)
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_holdings is True

    @pytest.mark.asyncio
    async def test_false_when_the_only_investment_is_archived(self, monkeypatch):
        # The probe is deliberately the active-only one. `exists_by_user` counts archived holdings for
        # onboarding, but an archived investment contributes nothing to portfolio value — so reusing it
        # here would claim the headline is derived from something when it is derived from nothing.
        self._patch(monkeypatch, accounts=[], investments=False, cards=False)
        monkeypatch.setattr(dashboard_service.investment_repository, "exists_by_user", AsyncMock(return_value=True))
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_holdings is False

    @pytest.mark.asyncio
    async def test_true_for_a_card_alone(self, monkeypatch):
        # A card-only user has no account to reconcile and nothing to snapshot, but their card debt is
        # still a net-worth input, so the dashboard must acknowledge them.
        self._patch(monkeypatch, accounts=[], investments=False, cards=True)
        result = await dashboard_service.get_overview(AsyncMock(), 1)
        assert result.has_holdings is True

    @pytest.mark.asyncio
    async def test_short_circuits_the_existence_queries_once_accounts_exist(self, monkeypatch):
        # The account side rides the list _load_cash_total already fetched; the other two are only
        # queried if it comes back empty, so holding an account costs no extra round trip.
        self._patch(monkeypatch, accounts=[_acct(1, "ARS")], investments=False, cards=False)
        await dashboard_service.get_overview(AsyncMock(), 1)
        dashboard_service.investment_repository.exists_active_by_user.assert_not_called()
        dashboard_service.credit_card_repository.exists_by_user.assert_not_called()
