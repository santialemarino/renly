# Pure calculation functions for investment and portfolio metrics.

import bisect
from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.currency import get_ars_pair, is_supported
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType

ZERO = Decimal("0")
ONE = Decimal("1")


# Computes period return between two snapshots, adjusting for net cash flow.
# Formula: (S_curr - NetCF) / S_prev - 1. Returns None if S_prev is zero.
def period_return(s_prev: Decimal, s_curr: Decimal, net_cf: Decimal) -> Decimal | None:
    if s_prev == ZERO:
        return None
    return (s_curr - net_cf) / s_prev - ONE


# Chains period returns into a time-weighted return (TWR).
# Formula: (1+r1)(1+r2)...(1+rN) - 1. Returns None if empty.
def twr(returns: list[Decimal]) -> Decimal | None:
    if not returns:
        return None
    product = ONE
    for r in returns:
        product *= ONE + r
    return product - ONE


# Computes net invested capital from transactions.
# Deposits and buys are inflows; sells and withdrawals are outflows.
def invested_capital(transactions: list[Transaction]) -> Decimal:
    total = ZERO
    for tx in transactions:
        if tx.type in (TransactionType.deposit, TransactionType.buy):
            total += tx.amount
        else:
            total -= tx.amount
    return total


# Computes net cash flow between two dates (exclusive start, inclusive end).
def net_cash_flow(
    transactions: list[Transaction],
    after: date_type,
    until: date_type,
) -> Decimal:
    total = ZERO
    for tx in transactions:
        if after < tx.date <= until:
            if tx.type in (TransactionType.deposit, TransactionType.buy):
                total += tx.amount
            else:
                total -= tx.amount
    return total


# Computes XIRR (annualised money-weighted return) via Newton-Raphson.
# cashflows: list of (date, amount) where outflows are negative, inflows positive.
# Returns None if it cannot converge or there are insufficient data points.
def xirr(
    cashflows: list[tuple[date_type, float]],
    guess: float = 0.1,
    max_iter: int = 200,
    tol: float = 1e-7,
) -> Decimal | None:
    if len(cashflows) < 2:
        return None

    d0 = cashflows[0][0]
    day_fracs = [(cf[0] - d0).days / 365.0 for cf in cashflows]
    amounts = [cf[1] for cf in cashflows]

    rate = guess
    for _ in range(max_iter):
        npv = sum(a / (1 + rate) ** t if t != 0 else a for a, t in zip(amounts, day_fracs))
        dnpv = sum(-t * a / (1 + rate) ** (t + 1) for a, t in zip(amounts, day_fracs) if t != 0)
        if abs(dnpv) < 1e-12:
            return None
        new_rate = rate - npv / dnpv
        if abs(new_rate - rate) < tol:
            return Decimal(str(round(new_rate, 6)))
        rate = new_rate

    return None


# Builds XIRR cashflows for an investment.
# First snapshot as outflow (negative), deposits as outflows, withdrawals as inflows,
# final snapshot as inflow (positive).
def build_irr_cashflows(
    snapshots: list[InvestmentSnapshot],
    transactions: list[Transaction],
) -> list[tuple[date_type, float]]:
    if not snapshots:
        return []

    first = snapshots[0]
    cashflows: list[tuple[date_type, float]] = [
        (first.date, -float(first.value)),
    ]

    for tx in transactions:
        if tx.date <= first.date:
            continue
        if tx.type in (TransactionType.deposit, TransactionType.buy):
            cashflows.append((tx.date, -float(tx.amount)))
        else:
            cashflows.append((tx.date, float(tx.amount)))

    last = snapshots[-1]
    if last.date != first.date:
        cashflows.append((last.date, float(last.value)))

    return cashflows


# Computes all period returns for an investment given snapshots and transactions.
# Returns list of (date, value, return_pct) tuples.
def compute_period_returns(
    snapshots: list[InvestmentSnapshot],
    transactions: list[Transaction],
) -> list[tuple[date_type, Decimal, Decimal | None]]:
    if not snapshots:
        return []

    results: list[tuple[date_type, Decimal, Decimal | None]] = [
        (snapshots[0].date, snapshots[0].value, None),
    ]

    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1]
        curr = snapshots[i]
        ncf = net_cash_flow(transactions, prev.date, curr.date)
        r = period_return(prev.value, curr.value, ncf)
        results.append((curr.date, curr.value, r))

    return results


# Groups snapshots by investment_id. Returns {investment_id: [snapshots sorted by date]}.
def group_snapshots_by_investment(
    snapshots: list[InvestmentSnapshot],
) -> dict[int, list[InvestmentSnapshot]]:
    grouped: dict[int, list[InvestmentSnapshot]] = defaultdict(list)
    for s in snapshots:
        grouped[s.investment_id].append(s)
    return dict(grouped)


# Groups transactions by investment_id. Returns {investment_id: [transactions sorted by date]}.
def group_transactions_by_investment(
    transactions: list[Transaction],
) -> dict[int, list[Transaction]]:
    grouped: dict[int, list[Transaction]] = defaultdict(list)
    for t in transactions:
        grouped[t.investment_id].append(t)
    return dict(grouped)


# Returns True if both currencies are supported (can be converted via USD pivot).
# Same currency always converts (identity).
def can_convert(from_currency: str, to_currency: str) -> bool:
    if from_currency == to_currency:
        return True
    return is_supported(from_currency) and is_supported(to_currency)


# Converts a value between any two supported currencies via USD as pivot.
# rate_map: {currency: Decimal} where each value is "1 USD = X <currency>".
# USD itself has an implicit rate of 1. Returns value unchanged if same or unsupported.
def convert_value(
    value: Decimal,
    from_currency: str,
    to_currency: str,
    rate_map: dict[str, Decimal],
) -> Decimal:
    if from_currency == to_currency:
        return value
    from_rate = rate_map.get(from_currency)
    to_rate = rate_map.get(to_currency)
    if from_rate is None or to_rate is None:
        return value
    return value / from_rate * to_rate


# Mapping from non-ARS currency code to its USD pair. ARS uses the dollar-preference pair.
_NON_ARS_PAIRS = {
    "BRL": ExchangeRatePair.USD_BRL,
    "EUR": ExchangeRatePair.USD_EUR,
    "GBP": ExchangeRatePair.USD_GBP,
}


# Per-request date-aware rate lookup (Phase 3, Step C — historical exchange rate conversion).
# Pre-fetches every stored rate once per request and serves a rate map for any historical date.
# For each pair we keep rates sorted by date and binary-search for "the latest rate where
# date <= as_of_date" (matches how a real bank-statement valuation looks back to the most recent
# quoted rate at or before the transaction date). If the requested as_of_date predates every
# stored rate for a pair, we fall back to the earliest available rate so the page never breaks —
# a deliberate trade-off: degraded historical accuracy for ancient dates beats a 503 page.
# Per-date rate maps are memoised so repeated lookups for the same date are O(1).
class RateLookup:
    def __init__(
        self,
        dollar_preference: str | None,
        rates_by_pair: dict[ExchangeRatePair, list[ExchangeRate]],
    ) -> None:
        self._dollar_preference = dollar_preference
        self._rates_by_pair = rates_by_pair
        # bisect needs a list of comparable keys; cache the date lists alongside the rate lists.
        self._dates_by_pair: dict[ExchangeRatePair, list[date_type]] = {pair: [r.date for r in rates] for pair, rates in rates_by_pair.items()}
        self._cache: dict[date_type, dict[str, Decimal] | None] = {}

    # Returns the rate map for as_of_date (latest rate where rate.date <= as_of_date per pair,
    # with earliest-available fallback). Returns None when no rates exist at all.
    def get_rate_map_at(self, as_of_date: date_type) -> dict[str, Decimal] | None:
        if as_of_date in self._cache:
            return self._cache[as_of_date]
        if not self._rates_by_pair:
            self._cache[as_of_date] = None
            return None

        rate_map: dict[str, Decimal] = {"USD": ONE}

        ars_pair = get_ars_pair(self._dollar_preference)
        ars_rate = self._lookup_pair(ars_pair, as_of_date)
        if ars_rate is None:
            # Fall back to MEP when the preferred pair has no stored rate (rather than
            # relying on `or`, which would also short-circuit on a hypothetical Decimal(0)).
            ars_rate = self._lookup_pair(ExchangeRatePair.USD_ARS_MEP, as_of_date)
        if ars_rate is not None:
            rate_map["ARS"] = ars_rate

        for currency_code, pair in _NON_ARS_PAIRS.items():
            rate = self._lookup_pair(pair, as_of_date)
            if rate is not None:
                rate_map[currency_code] = rate

        self._cache[as_of_date] = rate_map
        return rate_map

    # Binary-search the pair's sorted rates for the latest entry with date <= as_of_date.
    # Falls back to the earliest available rate when as_of_date predates all stored rates.
    def _lookup_pair(self, pair: ExchangeRatePair, as_of_date: date_type) -> Decimal | None:
        rates = self._rates_by_pair.get(pair)
        if not rates:
            return None
        dates = self._dates_by_pair[pair]
        idx = bisect.bisect_right(dates, as_of_date) - 1
        if idx >= 0:
            return rates[idx].rate
        # Pre-history fallback: use the earliest rate so display never breaks for ancient dates.
        return rates[0].rate


# Builds a RateLookup pre-loaded with every stored exchange rate. One DB round-trip per request;
# callers reuse the returned object across many per-row lookups.
async def build_rate_lookup(
    session: AsyncSession,
    dollar_preference: str | None = None,
) -> RateLookup:
    from app.repositories.exchange_rate_repository import exchange_rate_repository

    rates_by_pair = await exchange_rate_repository.get_all_grouped_by_pair(session)
    return RateLookup(dollar_preference, rates_by_pair)


# Backward-compat shim: returns the rate map valid TODAY. Equivalent to the previous
# implementation (latest stored rate per pair). New code should prefer build_rate_lookup +
# get_rate_map_at(row.date) so historical values stay deterministic across time.
async def get_rate_map(
    session: AsyncSession,
    dollar_preference: str | None = None,
) -> dict[str, Decimal] | None:
    lookup = await build_rate_lookup(session, dollar_preference)
    return lookup.get_rate_map_at(date_type.today())
