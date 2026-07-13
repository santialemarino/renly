from datetime import date
from decimal import Decimal

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.utils.metrics import (
    RateLookup,
    build_irr_cashflows,
    build_windowed_portfolio_cashflows,
    can_convert,
    compute_period_returns,
    convert_optional,
    convert_value,
    invested_capital,
    month_over_month,
    net_cash_flow,
    period_return,
    portfolio_totals_and_returns,
    portfolio_value_at,
    twr,
    xirr,
)

ZERO = Decimal("0")


def _snap(inv_id: int, d: date, value: str, currency: str = "USD") -> InvestmentSnapshot:
    return InvestmentSnapshot(investment_id=inv_id, date=d, value=Decimal(value), currency=currency)


def _tx(inv_id: int, d: date, amount: str, tx_type: TransactionType, currency: str = "USD") -> Transaction:
    return Transaction(investment_id=inv_id, date=d, amount=Decimal(amount), currency=currency, type=tx_type)


# --- period_return ---


class TestPeriodReturn:
    def test_simple_growth(self):
        r = period_return(Decimal("1000"), Decimal("1050"), ZERO)
        assert r == Decimal("0.05")

    def test_simple_loss(self):
        r = period_return(Decimal("1000"), Decimal("950"), ZERO)
        assert r == Decimal("-0.05")

    def test_with_deposit(self):
        # Value went from 1000 to 1200, but 100 was deposited.
        # Growth = (1200 - 100) / 1000 - 1 = 0.10.
        r = period_return(Decimal("1000"), Decimal("1200"), Decimal("100"))
        assert r == Decimal("0.1")

    def test_with_withdrawal(self):
        # Value went from 1000 to 850, but 200 was withdrawn.
        # Growth = (850 - (-200)) / 1000 - 1 = 0.05.
        r = period_return(Decimal("1000"), Decimal("850"), Decimal("-200"))
        assert r == Decimal("0.05")

    def test_zero_previous_returns_none(self):
        assert period_return(ZERO, Decimal("100"), ZERO) is None


# --- twr ---


class TestTWR:
    def test_chain_returns(self):
        # +5%, -2%, +4% -> 1.05 * 0.98 * 1.04 - 1 ≈ 0.07016
        returns = [Decimal("0.05"), Decimal("-0.02"), Decimal("0.04")]
        result = twr(returns)
        assert result is not None
        assert abs(result - Decimal("0.07016")) < Decimal("0.00001")

    def test_empty_returns_none(self):
        assert twr([]) is None

    def test_single_return(self):
        result = twr([Decimal("0.10")])
        assert result == Decimal("0.10")


# --- invested_capital ---


class TestInvestedCapital:
    def test_deposits_only(self):
        txs = [
            _tx(1, date(2025, 1, 1), "1000", TransactionType.deposit),
            _tx(1, date(2025, 2, 1), "500", TransactionType.deposit),
        ]
        assert invested_capital(txs) == Decimal("1500")

    def test_deposits_and_withdrawals(self):
        txs = [
            _tx(1, date(2025, 1, 1), "1000", TransactionType.deposit),
            _tx(1, date(2025, 2, 1), "200", TransactionType.withdrawal),
        ]
        assert invested_capital(txs) == Decimal("800")

    def test_buys_and_sells(self):
        txs = [
            _tx(1, date(2025, 1, 1), "1000", TransactionType.buy),
            _tx(1, date(2025, 3, 1), "300", TransactionType.sell),
        ]
        assert invested_capital(txs) == Decimal("700")

    def test_empty(self):
        assert invested_capital([]) == ZERO


# --- net_cash_flow ---


class TestNetCashFlow:
    def test_within_range(self):
        txs = [
            _tx(1, date(2025, 1, 15), "100", TransactionType.deposit),
            _tx(1, date(2025, 2, 10), "200", TransactionType.deposit),
            _tx(1, date(2025, 3, 5), "50", TransactionType.withdrawal),
        ]
        # Between Jan 31 and Feb 28: only the Feb 10 deposit counts.
        ncf = net_cash_flow(txs, date(2025, 1, 31), date(2025, 2, 28))
        assert ncf == Decimal("200")

    def test_exclusive_start_inclusive_end(self):
        txs = [
            _tx(1, date(2025, 1, 31), "100", TransactionType.deposit),
            _tx(1, date(2025, 2, 28), "200", TransactionType.deposit),
        ]
        # Start date is exclusive, end date is inclusive.
        ncf = net_cash_flow(txs, date(2025, 1, 31), date(2025, 2, 28))
        assert ncf == Decimal("200")


# --- compute_period_returns ---


class TestComputePeriodReturns:
    def test_three_months_no_flows(self):
        snaps = [
            _snap(1, date(2025, 1, 31), "1000"),
            _snap(1, date(2025, 2, 28), "1050"),
            _snap(1, date(2025, 3, 31), "1029"),
        ]
        results = compute_period_returns(snaps, [])
        assert len(results) == 3
        assert results[0][2] is None  # first has no return
        assert results[1][2] == Decimal("0.05")  # 1050/1000 - 1
        assert results[2][2] == Decimal("-0.02")  # 1029/1050 - 1

    def test_with_deposit(self):
        snaps = [
            _snap(1, date(2025, 1, 31), "1000"),
            _snap(1, date(2025, 2, 28), "1600"),
        ]
        txs = [_tx(1, date(2025, 2, 15), "500", TransactionType.deposit)]
        results = compute_period_returns(snaps, txs)
        # (1600 - 500) / 1000 - 1 = 0.10
        assert results[1][2] == Decimal("0.1")

    def test_empty_snapshots(self):
        assert compute_period_returns([], []) == []


# --- xirr ---


class TestXIRR:
    def test_simple_growth(self):
        # Invest 1000, get back 1100 after 1 year -> ~10% annual return.
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2026, 1, 1), 1100.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert abs(result - Decimal("0.1")) < Decimal("0.001")

    def test_with_intermediate_deposit(self):
        # Invest 1000, add 500 at 6 months, final value 1600 at 1 year.
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2025, 7, 1), -500.0),
            (date(2026, 1, 1), 1600.0),
        ]
        result = xirr(cfs)
        assert result is not None
        # Should be a positive return.
        assert result > ZERO

    def test_insufficient_data(self):
        assert xirr([]) is None
        assert xirr([(date(2025, 1, 1), -1000.0)]) is None

    def test_deep_negative_rate(self):
        # 1000 in, 550 back exactly one year later: 550 / (1 + r) = 1000 -> r = -0.45.
        # The old unbracketed Newton converged to the pole at -1 (-100%) for this shape.
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2026, 1, 1), 550.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert abs(result - Decimal("-0.45")) < Decimal("0.0001")

    def test_deep_loss_converges(self):
        # 1800 in over two dates, 50 back: near-total loss. The old Newton produced complex
        # intermediates here; the bracketed root is -0.993133 (NPV(-0.993133) ~ 0).
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2025, 6, 1), -800.0),
            (date(2026, 1, 1), 50.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert abs(result - Decimal("-0.993133")) < Decimal("0.0001")

    def test_span_under_30_days_returns_none(self):
        # 29-day span: annualisation suppressed (MIN_IRR_SPAN_DAYS).
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2025, 1, 30), 1010.0),
        ]
        assert xirr(cfs) is None

    def test_span_of_exactly_30_days_computes(self):
        # 30-day span passes the guard: (1010/1000)^(365/30) - 1 = 1.01^12.1666... - 1 = 0.128695.
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2025, 1, 31), 1010.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert abs(result - Decimal("0.128695")) < Decimal("0.0001")

    def test_all_same_sign_returns_none(self):
        # No IRR exists without both inflows and outflows.
        assert xirr([(date(2025, 1, 1), -100.0), (date(2025, 6, 1), -200.0)]) is None
        assert xirr([(date(2025, 1, 1), 100.0), (date(2025, 6, 1), 200.0)]) is None

    def test_multi_crossing_series_suppressed(self):
        # A non-conventional series whose cumulative cash flow crosses zero more than once
        # (-1000 -> +4000 -> -2000 -> +1000) can admit several real IRRs, so the bracketed
        # root would be accidental. The well-definedness guard suppresses it (None) before
        # bisection — which also keeps the old fuzzing crash class (complex intermediates)
        # unreachable. TWR carries the return for such series.
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2025, 2, 1), 5000.0),
            (date(2025, 3, 1), -6000.0),
            (date(2026, 1, 1), 3000.0),
        ]
        assert xirr(cfs) is None

    def test_break_even_is_unique(self):
        # Cumulative ends at exactly zero (no strict positive crossing) yet the IRR is a
        # unique 0%: the guard keeps it (crossings <= 1), never suppressing a flat holding.
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2026, 1, 1), 1000.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert abs(result) < Decimal("0.0001")

    def test_single_crossing_with_intermediate_withdrawal_kept(self):
        # Mid-stream withdrawal then a larger terminal inflow: three flow sign changes but the
        # cumulative (-1000 -> -700 -> -900 -> +400) crosses zero once, so the IRR is unique
        # by Norström and is reported (not suppressed).
        cfs = [
            (date(2025, 1, 1), -1000.0),
            (date(2025, 5, 1), 300.0),
            (date(2025, 9, 1), -200.0),
            (date(2026, 1, 1), 1400.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert result > ZERO

    def test_unsorted_input_is_sorted_internally(self):
        # Portfolio series concatenate per-investment flows; result must not depend on order.
        cfs = [
            (date(2026, 1, 1), 1100.0),
            (date(2025, 1, 1), -1000.0),
        ]
        result = xirr(cfs)
        assert result is not None
        assert abs(result - Decimal("0.1")) < Decimal("0.001")


# --- build_irr_cashflows ---


class TestBuildIRRCashflows:
    def test_basic(self):
        snaps = [
            _snap(1, date(2025, 1, 31), "1000"),
            _snap(1, date(2025, 3, 31), "1100"),
        ]
        txs = [_tx(1, date(2025, 2, 15), "200", TransactionType.deposit)]
        cfs = build_irr_cashflows(snaps, txs)
        assert len(cfs) == 3
        assert cfs[0] == (date(2025, 1, 31), -1000.0)
        assert cfs[1] == (date(2025, 2, 15), -200.0)
        assert cfs[2] == (date(2025, 3, 31), 1100.0)

    def test_with_withdrawal(self):
        snaps = [
            _snap(1, date(2025, 1, 31), "1000"),
            _snap(1, date(2025, 3, 31), "900"),
        ]
        txs = [_tx(1, date(2025, 2, 15), "200", TransactionType.withdrawal)]
        cfs = build_irr_cashflows(snaps, txs)
        assert cfs[1] == (date(2025, 2, 15), 200.0)

    def test_empty_snapshots(self):
        assert build_irr_cashflows([], []) == []

    def test_single_snapshot(self):
        snaps = [_snap(1, date(2025, 1, 31), "1000")]
        cfs = build_irr_cashflows(snaps, [])
        # A lone snapshot would be a same-day in/out pair carrying no rate information.
        assert cfs == []

    def test_single_snapshot_with_later_transaction(self):
        snaps = [_snap(1, date(2025, 1, 31), "1000")]
        txs = [_tx(1, date(2025, 3, 15), "200", TransactionType.deposit)]
        cfs = build_irr_cashflows(snaps, txs)
        # Terminal value dated at the last transaction so the deposit doesn't dangle unvalued.
        assert cfs == [
            (date(2025, 1, 31), -1000.0),
            (date(2025, 3, 15), -200.0),
            (date(2025, 3, 15), 1000.0),
        ]

    def test_trailing_transaction_after_last_snapshot(self):
        snaps = [
            _snap(1, date(2025, 1, 31), "1000"),
            _snap(1, date(2025, 3, 31), "1100"),
        ]
        txs = [_tx(1, date(2025, 4, 15), "300", TransactionType.withdrawal)]
        cfs = build_irr_cashflows(snaps, txs)
        # The withdrawal after the last snapshot pushes the terminal date to the tx date.
        assert cfs == [
            (date(2025, 1, 31), -1000.0),
            (date(2025, 4, 15), 300.0),
            (date(2025, 4, 15), 1100.0),
        ]


# --- portfolio_totals_and_returns ---


class TestPortfolioTotalsAndReturns:
    def test_first_snapshot_is_capital_not_return(self):
        # A: 1000 -> 1010 (+1%); B appears with a first snapshot of 500 in the same period.
        # Totals go 1000 -> 1510 but 500 is contributed capital:
        # r = (1510 - 500) / 1000 - 1 = 0.01, NOT 1510/1000 - 1 = 0.51 (the audit's +51% bug).
        idv = {
            1: {date(2025, 1, 31): Decimal("1000"), date(2025, 2, 28): Decimal("1010")},
            2: {date(2025, 2, 28): Decimal("500")},
        }
        totals, returns = portfolio_totals_and_returns(idv, {1: [], 2: []})
        assert totals == [
            (date(2025, 1, 31), Decimal("1000")),
            (date(2025, 2, 28), Decimal("1510")),
        ]
        assert returns == [(date(2025, 2, 28), Decimal("0.01"))]
        assert twr([r for _, r in returns if r is not None]) == Decimal("0.01")

    def test_flow_on_first_snapshot_date_not_double_counted(self):
        # B's first snapshot day also has a real 500 deposit: the deposit is embodied in the
        # first value, so the synthetic inflow must not stack with it (still 0.01, not -0.32).
        idv = {
            1: {date(2025, 1, 31): Decimal("1000"), date(2025, 2, 28): Decimal("1010")},
            2: {date(2025, 2, 28): Decimal("500")},
        }
        flows = {1: [], 2: [(date(2025, 2, 28), Decimal("500"))]}
        _, returns = portfolio_totals_and_returns(idv, flows)
        assert returns == [(date(2025, 2, 28), Decimal("0.01"))]

    def test_mid_period_deposit(self):
        # 1000 -> 1100 with a 50 deposit inside the period: r = (1100 - 50) / 1000 - 1 = 0.05.
        idv = {1: {date(2025, 1, 31): Decimal("1000"), date(2025, 2, 28): Decimal("1100")}}
        flows = {1: [(date(2025, 2, 10), Decimal("50"))]}
        _, returns = portfolio_totals_and_returns(idv, flows)
        assert returns == [(date(2025, 2, 28), Decimal("0.05"))]

    def test_flow_before_first_snapshot_ignored(self):
        # B's deposit predates its first snapshot -> embodied in that first value; the period
        # books only the synthetic 300 inflow: r = (1350 - 300) / 1000 - 1 = 0.05.
        idv = {
            1: {date(2025, 1, 31): Decimal("1000"), date(2025, 2, 28): Decimal("1050")},
            2: {date(2025, 2, 28): Decimal("300")},
        }
        flows = {2: [(date(2025, 2, 10), Decimal("300"))]}
        totals, returns = portfolio_totals_and_returns(idv, flows)
        assert totals == [
            (date(2025, 1, 31), Decimal("1000")),
            (date(2025, 2, 28), Decimal("1350")),
        ]
        assert returns == [(date(2025, 2, 28), Decimal("0.05"))]

    def test_empty(self):
        assert portfolio_totals_and_returns({}, {}) == ([], [])


# --- portfolio_value_at ---


class TestPortfolioValueAt:
    TOTALS = [
        (date(2025, 1, 31), Decimal("1000")),
        (date(2025, 6, 30), Decimal("1150")),
    ]

    def test_forward_fills_between_entries(self):
        assert portfolio_value_at(self.TOTALS, date(2025, 3, 31)) == Decimal("1000")

    def test_exact_date(self):
        assert portfolio_value_at(self.TOTALS, date(2025, 6, 30)) == Decimal("1150")

    def test_before_all_data_returns_zero(self):
        assert portfolio_value_at(self.TOTALS, date(2024, 12, 31)) == ZERO


# --- month_over_month ---


class TestMonthOverMonth:
    def test_prior_month_end_selected(self):
        # Previous = last value before Feb 1 (the Jan 31 total), current = latest entry.
        series = [
            (date(2025, 1, 31), Decimal("1000")),
            (date(2025, 2, 15), Decimal("1040")),
            (date(2025, 2, 28), Decimal("1510")),
        ]
        assert month_over_month(series) == (Decimal("1000"), Decimal("1510"))

    def test_single_month_history_returns_none(self):
        series = [
            (date(2025, 2, 1), Decimal("100")),
            (date(2025, 2, 28), Decimal("120")),
        ]
        assert month_over_month(series) is None

    def test_empty_returns_none(self):
        assert month_over_month([]) is None


# --- build_windowed_portfolio_cashflows ---


class TestBuildWindowedPortfolioCashflows:
    IDV = {
        1: {
            date(2025, 1, 31): Decimal("1000"),
            date(2025, 6, 30): Decimal("1150"),
            date(2025, 12, 31): Decimal("1300"),
        }
    }
    TOTALS = [
        (date(2025, 1, 31), Decimal("1000")),
        (date(2025, 6, 30), Decimal("1150")),
        (date(2025, 12, 31), Decimal("1300")),
    ]
    FLOWS = {1: [(date(2025, 3, 15), Decimal("100"))]}

    def test_boundaries_replace_out_of_window_flows(self):
        # Window (Mar 31, Dec 31]: the inception outflow and the Mar 15 deposit are outside;
        # they collapse into the forward-filled start valuation (1000 as of Mar 31).
        cfs = build_windowed_portfolio_cashflows(self.TOTALS, self.IDV, self.FLOWS, date(2025, 3, 31), date(2025, 12, 31))
        assert cfs == [
            (date(2025, 3, 31), -1000.0),
            (date(2025, 12, 31), 1300.0),
        ]

    def test_in_window_flow_included(self):
        cfs = build_windowed_portfolio_cashflows(self.TOTALS, self.IDV, self.FLOWS, date(2025, 2, 1), date(2025, 12, 31))
        assert cfs == [
            (date(2025, 2, 1), -1000.0),
            (date(2025, 3, 15), -100.0),
            (date(2025, 12, 31), 1300.0),
        ]

    def test_investment_born_inside_window_is_outflow(self):
        idv = {**self.IDV, 2: {date(2025, 6, 30): Decimal("500")}}
        totals = [
            (date(2025, 1, 31), Decimal("1000")),
            (date(2025, 6, 30), Decimal("1650")),
            (date(2025, 12, 31), Decimal("1800")),
        ]
        cfs = build_windowed_portfolio_cashflows(totals, idv, self.FLOWS, date(2025, 2, 1), date(2025, 12, 31))
        assert cfs == [
            (date(2025, 2, 1), -1000.0),
            (date(2025, 3, 15), -100.0),
            (date(2025, 6, 30), -500.0),
            (date(2025, 12, 31), 1800.0),
        ]

    def test_no_start_includes_inception(self):
        # Open-start window: start value is zero, so the first snapshot enters as an outflow.
        cfs = build_windowed_portfolio_cashflows(self.TOTALS, self.IDV, self.FLOWS, None, date(2025, 6, 30))
        assert cfs == [
            (date(2025, 1, 31), -1000.0),
            (date(2025, 3, 15), -100.0),
            (date(2025, 6, 30), 1150.0),
        ]

    def test_window_before_all_data_returns_empty(self):
        cfs = build_windowed_portfolio_cashflows(self.TOTALS, self.IDV, self.FLOWS, date(2024, 1, 1), date(2024, 6, 1))
        assert cfs == []

    def test_trailing_in_window_flow_dates_terminal(self):
        # A withdrawal after the last snapshot but inside the window moves the terminal inflow
        # to the flow date so the series stays chronologically bracketed.
        totals = [(date(2025, 1, 31), Decimal("1000")), (date(2025, 2, 28), Decimal("1100"))]
        idv = {1: {date(2025, 1, 31): Decimal("1000"), date(2025, 2, 28): Decimal("1100")}}
        flows = {1: [(date(2025, 3, 10), Decimal("-300"))]}
        cfs = build_windowed_portfolio_cashflows(totals, idv, flows, date(2025, 2, 1), date(2025, 3, 15))
        assert cfs == [
            (date(2025, 2, 1), -1000.0),
            (date(2025, 3, 10), 300.0),
            (date(2025, 3, 10), 1100.0),
        ]


# --- can_convert ---


class TestCanConvert:
    def test_same_currency(self):
        assert can_convert("USD", "USD") is True

    def test_usd_ars(self):
        assert can_convert("USD", "ARS") is True

    def test_eur_ars_via_pivot(self):
        assert can_convert("EUR", "ARS") is True

    def test_brl_gbp_via_pivot(self):
        assert can_convert("BRL", "GBP") is True

    def test_unsupported_currency(self):
        assert can_convert("CHF", "ARS") is False

    def test_both_unsupported(self):
        assert can_convert("CHF", "JPY") is False


# --- convert_value ---


class TestConvertValue:
    # Rate map: 1 USD = 1400 ARS, 1 USD = 0.92 EUR, 1 USD = 5.5 BRL, 1 USD = 0.79 GBP.
    RATE_MAP = {
        "USD": Decimal("1"),
        "ARS": Decimal("1400"),
        "EUR": Decimal("0.92"),
        "BRL": Decimal("5.5"),
        "GBP": Decimal("0.79"),
    }

    def test_usd_to_ars(self):
        result = convert_value(Decimal("100"), "USD", "ARS", self.RATE_MAP)
        assert result == Decimal("140000")

    def test_ars_to_usd(self):
        result = convert_value(Decimal("140000"), "ARS", "USD", self.RATE_MAP)
        assert result == Decimal("100")

    def test_same_currency(self):
        result = convert_value(Decimal("100"), "USD", "USD", self.RATE_MAP)
        assert result == Decimal("100")

    def test_missing_source_rate_returns_none(self):
        # CHF is not in the rate map — fail loud, never pass the value through.
        assert convert_value(Decimal("100"), "CHF", "ARS", self.RATE_MAP) is None

    def test_missing_target_rate_returns_none(self):
        assert convert_value(Decimal("100"), "USD", "CHF", self.RATE_MAP) is None

    def test_eur_to_ars_via_pivot(self):
        # 100 EUR → USD: 100 / 0.92 = 108.6956... . USD → ARS: * 1400 = 152173.9130... .
        # Quantized to 2 places.
        result = convert_value(Decimal("100"), "EUR", "ARS", self.RATE_MAP)
        assert result == Decimal("152173.91")

    def test_brl_to_gbp_via_pivot(self):
        # 550 BRL → USD: 550 / 5.5 = 100. USD → GBP: 100 * 0.79 = 79.
        result = convert_value(Decimal("550"), "BRL", "GBP", self.RATE_MAP)
        assert result == Decimal("79.00")

    def test_eur_to_usd(self):
        # 100 EUR → USD: 100 / 0.92 = 108.6956... . Quantized to 2 places (banker's rounding -> .70).
        result = convert_value(Decimal("100"), "EUR", "USD", self.RATE_MAP)
        assert result == Decimal("108.70")


# --- convert_optional ---


def _lookup_with_mep(rate: str) -> RateLookup:
    rates = {
        ExchangeRatePair.USD_ARS_MEP: [
            ExchangeRate(date=date(2026, 1, 1), pair=ExchangeRatePair.USD_ARS_MEP, rate=Decimal(rate), source="test"),
        ],
    }
    return RateLookup(dollar_preference="mep", rates_by_pair=rates)


class TestConvertOptional:
    def test_no_target_currency_returns_none(self):
        assert convert_optional(Decimal("100"), "USD", None, _lookup_with_mep("1000"), date(2026, 1, 15)) is None

    def test_same_currency_returns_value_without_lookup(self):
        assert convert_optional(Decimal("100"), "USD", "USD", None, date(2026, 1, 15)) == Decimal("100")

    def test_missing_lookup_returns_none(self):
        assert convert_optional(Decimal("100"), "USD", "ARS", None, date(2026, 1, 15)) is None

    def test_empty_lookup_returns_none(self):
        empty = RateLookup(dollar_preference="mep", rates_by_pair={})
        assert convert_optional(Decimal("100"), "USD", "ARS", empty, date(2026, 1, 15)) is None

    def test_converts_at_the_given_date(self):
        result = convert_optional(Decimal("100"), "USD", "ARS", _lookup_with_mep("1000"), date(2026, 1, 15))
        assert result == Decimal("100000.00")

    def test_missing_rate_returns_none(self):
        # Lookup only stores the MEP pair — EUR has no rate, so conversion must yield null.
        assert convert_optional(Decimal("100"), "EUR", "ARS", _lookup_with_mep("1000"), date(2026, 1, 15)) is None
