from datetime import date
from decimal import Decimal

from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.services.metrics_helpers import (
    build_irr_cashflows,
    can_convert,
    compute_period_returns,
    convert_value,
    invested_capital,
    net_cash_flow,
    period_return,
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
        # Only one snapshot, first == last, so only the initial outflow.
        assert len(cfs) == 1


# --- can_convert ---


class TestCanConvert:
    def test_same_currency(self):
        assert can_convert("USD", "USD") is True

    def test_same_base_usd_variant(self):
        assert can_convert("USD_MEP", "USD") is True

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

    def test_unsupported_pair_returns_unchanged(self):
        # CHF is not in the rate map, so no conversion possible.
        result = convert_value(Decimal("100"), "CHF", "ARS", self.RATE_MAP)
        assert result == Decimal("100")

    def test_eur_to_ars_via_pivot(self):
        # 100 EUR → USD: 100 / 0.92. USD → ARS: * 1400.
        result = convert_value(Decimal("100"), "EUR", "ARS", self.RATE_MAP)
        expected = Decimal("100") / Decimal("0.92") * Decimal("1400")
        assert result == expected

    def test_brl_to_gbp_via_pivot(self):
        # 550 BRL → USD: 550 / 5.5 = 100. USD → GBP: 100 * 0.79 = 79.
        result = convert_value(Decimal("550"), "BRL", "GBP", self.RATE_MAP)
        expected = Decimal("550") / Decimal("5.5") * Decimal("0.79")
        assert result == expected

    def test_usd_variant_to_ars(self):
        # USD_MEP resolves to base "USD", so 100 USD_MEP → ARS = 100 * 1400.
        result = convert_value(Decimal("100"), "USD_MEP", "ARS", self.RATE_MAP)
        assert result == Decimal("140000")

    def test_eur_to_usd(self):
        # 100 EUR → USD: 100 / 0.92.
        result = convert_value(Decimal("100"), "EUR", "USD", self.RATE_MAP)
        expected = Decimal("100") / Decimal("0.92") * Decimal("1")
        assert result == expected
