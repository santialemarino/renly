# Pure calculation functions and data structures for investment and portfolio metrics.
# Nothing in this module touches the DB — rate loading lives in the service layer
# (exchange_rate_service.build_rate_lookup / get_user_rate_lookup).

import bisect
from collections import defaultdict
from datetime import date as date_type
from decimal import Decimal

from app.domain.currency import get_ars_pair, is_supported
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType

ZERO = Decimal("0")
ONE = Decimal("1")

# Minimum cashflow span for an annualised IRR; annualising a shorter span produces absurd rates.
MIN_IRR_SPAN_DAYS = 30


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


# Computes XIRR (annualised money-weighted return) via bisection on the NPV sign change.
# cashflows: list of (date, amount) where outflows are negative, inflows positive; any order.
# Returns None when there are insufficient data points, the span is under MIN_IRR_SPAN_DAYS,
# all amounts share one sign, or no bracketing interval with an NPV sign change exists.
def xirr(
    cashflows: list[tuple[date_type, float]],
    max_iter: int = 200,
    tol: float = 1e-7,
) -> Decimal | None:
    if len(cashflows) < 2:
        return None

    ordered = sorted(cashflows, key=lambda cf: cf[0])
    d0 = ordered[0][0]
    day_fracs = [(cf[0] - d0).days / 365.0 for cf in ordered]
    amounts = [cf[1] for cf in ordered]

    # Annualising over a very short span produces absurd rates; suppress below the minimum.
    if (ordered[-1][0] - d0).days < MIN_IRR_SPAN_DAYS:
        return None

    # An IRR only exists when the series has both inflows and outflows.
    if all(a >= 0 for a in amounts) or all(a <= 0 for a in amounts):
        return None

    # Well-definedness guard (Norström's criterion). A money-weighted return is only
    # unambiguous when the time-ordered cumulative cash flow crosses zero at most once. A
    # non-conventional series (e.g. invest -> withdraw more than invested -> reinvest) can
    # cross repeatedly and admit several real IRRs, so bisection would return a
    # bracket-accidental one; suppress those (None) and let TWR — timing-independent — carry
    # the return. Break-even and simple gain/loss series never cross more than once, so they
    # still report their unique rate. An exact-zero cumulative carries no sign; a later flow
    # resolves the direction.
    #
    # Accumulate in Decimal, not float: the flows are 2-dp money (built via float(Decimal(...))),
    # so a mid-series balance that nets to exactly zero cancels cleanly in Decimal and is read as a
    # zero-touch (skipped, no crossing). Summed in float it lands on a ~1e-14 residue whose sign
    # fabricates two spurious crossings, which would wrongly suppress a genuinely unique IRR.
    cumulative = ZERO
    prev_sign = 0
    crossings = 0
    for a in amounts:
        cumulative += Decimal(str(a))
        sign = 1 if cumulative > 0 else -1 if cumulative < 0 else 0
        if sign == 0:
            continue
        if prev_sign != 0 and sign != prev_sign:
            crossings += 1
        prev_sign = sign
    if crossings > 1:
        return None

    # NPV of the series at a given rate; rate > -1 keeps every power real.
    def npv(rate: float) -> float:
        return sum(a / (1.0 + rate) ** t for a, t in zip(amounts, day_fracs))

    try:
        lo, hi = -0.9999, 10.0
        npv_lo = npv(lo)
        npv_hi = npv(hi)
        # Expand the upper bracket for extreme positive rates before giving up. NPV tends to the
        # earliest cashflow as rate grows and to a huge value of the latest cashflow's sign as
        # rate approaches -1, so a realistic series changes sign somewhere in between.
        while npv_lo * npv_hi > 0 and hi < 1e6:
            hi *= 10.0
            npv_hi = npv(hi)
        if npv_lo * npv_hi > 0:
            return None
        for _ in range(max_iter):
            mid = (lo + hi) / 2.0
            npv_mid = npv(mid)
            if abs(npv_mid) < tol or (hi - lo) / 2.0 < tol:
                return Decimal(str(round(mid, 6)))
            if npv_lo * npv_mid < 0:
                hi = mid
            else:
                lo = mid
                npv_lo = npv_mid
        return Decimal(str(round((lo + hi) / 2.0, 6)))
    except (OverflowError, ValueError, ZeroDivisionError):
        return None


# Builds XIRR cashflows for an investment.
# First snapshot as outflow (negative), deposits as outflows, withdrawals as inflows, and the
# terminal snapshot value as an inflow dated max(last snapshot date, last transaction date) so
# trailing transactions never dangle past the terminal value. A series whose terminal date
# equals the first date (one snapshot, no later transactions) carries no rate information → [].
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

    last_event_date = first.date
    for tx in transactions:
        if tx.date <= first.date:
            continue
        if tx.type in (TransactionType.deposit, TransactionType.buy):
            cashflows.append((tx.date, -float(tx.amount)))
        else:
            cashflows.append((tx.date, float(tx.amount)))
        if tx.date > last_event_date:
            last_event_date = tx.date

    last = snapshots[-1]
    terminal_date = max(last.date, last_event_date)
    if terminal_date == first.date:
        return []
    cashflows.append((terminal_date, float(last.value)))

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


# Forward-fills per-investment snapshot values into portfolio totals per date and chains
# period returns. A new investment's first snapshot value counts as a cash inflow in the
# period where it appears (contributed capital, not return); flows dated on or before an
# investment's first snapshot are ignored as already embodied in that first value.
# inv_date_value: {investment_id: {date: value}} (values already in display currency).
# flows_by_inv: {investment_id: [(date, signed amount)]} — positive = money in, negative = out.
# Returns (totals, returns): [(date, portfolio total)] and [(date, period return or None)].
def portfolio_totals_and_returns(
    inv_date_value: dict[int, dict[date_type, Decimal]],
    flows_by_inv: dict[int, list[tuple[date_type, Decimal]]],
) -> tuple[list[tuple[date_type, Decimal]], list[tuple[date_type, Decimal | None]]]:
    all_dates = sorted({d for dv in inv_date_value.values() for d in dv})
    if not all_dates:
        return [], []
    first_snap_date = {inv_id: min(dv) for inv_id, dv in inv_date_value.items() if dv}

    last_known: dict[int, Decimal] = {}
    totals: list[tuple[date_type, Decimal]] = []
    for d in all_dates:
        total = ZERO
        for inv_id, dv in inv_date_value.items():
            if d in dv:
                last_known[inv_id] = dv[d]
            total += last_known.get(inv_id, ZERO)
        totals.append((d, total))

    returns: list[tuple[date_type, Decimal | None]] = []
    for i in range(1, len(totals)):
        prev_date, prev_val = totals[i - 1]
        curr_date, curr_val = totals[i]
        period_ncf = ZERO
        for inv_id, flows in flows_by_inv.items():
            first_date = first_snap_date.get(inv_id)
            for flow_date, amount in flows:
                if first_date is not None and flow_date <= first_date:
                    continue
                if prev_date < flow_date <= curr_date:
                    period_ncf += amount
        for inv_id, first_date in first_snap_date.items():
            if prev_date < first_date <= curr_date:
                period_ncf += inv_date_value[inv_id][first_date]
        returns.append((curr_date, period_return(prev_val, curr_val, period_ncf)))
    return totals, returns


# Forward-filled portfolio value at as_of_date: the last total dated on or before it.
# Returns ZERO when the series has no entry that early.
def portfolio_value_at(
    portfolio_totals: list[tuple[date_type, Decimal]],
    as_of_date: date_type,
) -> Decimal:
    value = ZERO
    for d, total in portfolio_totals:
        if d > as_of_date:
            break
        value = total
    return value


# Selects the latest value and the last value dated before the latest entry's month from a
# chronological (date, value) series. Returns (previous, current), or None when the series
# has no entry before the latest month (nothing to compare against).
def month_over_month(
    series: list[tuple[date_type, Decimal]],
) -> tuple[Decimal, Decimal] | None:
    if not series:
        return None
    curr_date, curr_value = series[-1]
    month_start = date_type(curr_date.year, curr_date.month, 1)
    prev_values = [v for d, v in series if d < month_start]
    if not prev_values:
        return None
    return prev_values[-1], curr_value


# Builds the money-weighted cashflow series for a date-windowed portfolio IRR: an outflow of
# the forward-filled portfolio value at the window start, real flows and first-snapshot
# outflows inside the window, and an inflow of the forward-filled value at the window end
# (dated at the latest data or flow date inside the window). Zero boundary values are omitted.
# Same argument shapes as portfolio_totals_and_returns.
def build_windowed_portfolio_cashflows(
    portfolio_totals: list[tuple[date_type, Decimal]],
    inv_date_value: dict[int, dict[date_type, Decimal]],
    flows_by_inv: dict[int, list[tuple[date_type, Decimal]]],
    start_date: date_type | None,
    end_date: date_type | None,
) -> list[tuple[date_type, float]]:
    if not portfolio_totals:
        return []

    start_value = portfolio_value_at(portfolio_totals, start_date) if start_date else ZERO
    end_value = ZERO
    end_value_date: date_type | None = None
    for d, total in portfolio_totals:
        if end_date is not None and d > end_date:
            break
        end_value = total
        end_value_date = d
    if end_value_date is None:
        return []

    # True when d falls inside the (start, end] window.
    def _in_window(d: date_type) -> bool:
        if start_date and d <= start_date:
            return False
        if end_date and d > end_date:
            return False
        return True

    cashflows: list[tuple[date_type, float]] = []
    if start_date and start_value > ZERO:
        cashflows.append((start_date, -float(start_value)))

    first_snap_date = {inv_id: min(dv) for inv_id, dv in inv_date_value.items() if dv}
    last_flow_date = end_value_date
    for inv_id, first_date in first_snap_date.items():
        if _in_window(first_date):
            cashflows.append((first_date, -float(inv_date_value[inv_id][first_date])))
            last_flow_date = max(last_flow_date, first_date)
    for inv_id, flows in flows_by_inv.items():
        first_date = first_snap_date.get(inv_id)
        for flow_date, amount in flows:
            if first_date is not None and flow_date <= first_date:
                continue
            if _in_window(flow_date):
                cashflows.append((flow_date, -float(amount)))
                last_flow_date = max(last_flow_date, flow_date)

    if end_value > ZERO:
        cashflows.append((max(end_value_date, last_flow_date), float(end_value)))

    return sorted(cashflows, key=lambda cf: cf[0])


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
# USD itself has an implicit rate of 1. Returns the value unchanged when currencies match;
# returns None when either rate is missing from the map — callers must SKIP the row and surface
# it in a skipped list, never sum the unconverted value (fail-loud).
# The result is quantized to 2 decimal places: every response schema field that holds a
# converted amount declares `decimal_places=2, max_digits=18`, and the raw `value /
# from_rate * to_rate` runs under Python's default 28-digit Decimal precision — which
# produces 26-digit results on non-terminating divisions (e.g. ARS -> BRL via USD).
# Without quantization those overflow the Pydantic validator and surface as 500s.
def convert_value(
    value: Decimal,
    from_currency: str,
    to_currency: str,
    rate_map: dict[str, Decimal],
) -> Decimal | None:
    if from_currency == to_currency:
        return value
    from_rate = rate_map.get(from_currency)
    to_rate = rate_map.get(to_currency)
    if from_rate is None or to_rate is None:
        return None
    return (value / from_rate * to_rate).quantize(Decimal("0.01"))


# Converts a value into the requested display currency at the rate in effect on as_of_date.
# The shared per-row conversion used by every service that fills a converted_* response field.
# Returns None when no display currency was requested, when no rates are stored, or when the
# needed rate is missing (the caller leaves the converted field null and flags the row's currency
# in the response's skipped list); returns value unchanged when currencies match.
def convert_optional(
    value: Decimal,
    from_currency: str,
    target_currency: str | None,
    lookup: "RateLookup | None",
    as_of_date: date_type,
) -> Decimal | None:
    if not target_currency:
        return None
    if from_currency == target_currency:
        return value
    if lookup is None:
        return None
    rate_map = lookup.get_rate_map_at(as_of_date)
    if rate_map is None:
        return None
    return convert_value(value, from_currency, target_currency, rate_map)


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
