# Business logic for exchange rates: querying stored rates, fetching the latest quotes, and filling
# missing days from the history providers. Provider-specific logic (URLs, parsing, field mapping) lives
# in exchange_rate_providers.py.

import asyncio
import logging
import time
from collections.abc import Sequence
from datetime import date as date_type
from datetime import timedelta
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.currency import SUPPORTED_CURRENCIES, RatePoint
from app.domain.money import quantize
from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.repositories.exchange_rate_repository import ExchangeRateRow, exchange_rate_repository
from app.schemas.exchange_rate import ExchangeRateResponse, LatestRatesResponse, SupportedCurrenciesResponse
from app.services import settings_service
from app.services.exchange_rate_providers import (
    EXCHANGE_RATE_HISTORY_PROVIDERS,
    EXCHANGE_RATE_PROVIDERS,
    ExchangeRateHistoryProviderInfo,
    ExchangeRateHistoryUnavailable,
    ExchangeRateQuote,
)
from app.utils.metrics import RateLookup

logger = logging.getLogger(__name__)

# How far back the scheduled job looks for missing weekdays: the day before today and the
# GAP_FILL_WINDOW_DAYS - 1 before it. Covers an outage of up to three months on its own; anything
# older is the one-off backfill command's job (app/scripts/backfill_exchange_rates.py).
GAP_FILL_WINDOW_DAYS = 90

# Days fetched before a range's first day, so the quote in force on that day is known: the
# misdated-row check compares a stored rate with the quote before its date. Spans a long weekend
# plus a run of holidays.
HISTORY_CONTEXT_DAYS = 10

# The column's scale (NUMERIC(18, 6)); quotes are rounded to it (half-up, as Postgres stores them) before
# they are compared with stored rates.
_RATE_QUANTUM = Decimal("0.000001")

# The sources the LATEST providers store under. Before quotes carried their own date, these rows were
# stamped with the server's date, so only they can be a stale quote under a later date.
LATEST_SOURCES = frozenset(provider.source for provider in EXCHANGE_RATE_PROVIDERS)

# Process-level TTL cache for the grouped-rates load that backs every RateLookup. Rates are global
# (not per-user) and only change when the 6-hourly scheduler stores fresh quotes, so a short TTL
# plus the explicit invalidation below stops every converting endpoint from re-reading the whole
# exchange_rates table per request (a dashboard view = up to 7 full-table loads today). Cached
# entries are immutable (date, rate) tuples — safe to share across requests.
RATES_CACHE_TTL_SECONDS = 600

_rates_cache: dict[ExchangeRatePair, list[RatePoint]] | None = None
_rates_cache_loaded_at: float | None = None


# Returns the latest rates from the DB for all pairs.
async def get_latest_rates(session: AsyncSession) -> LatestRatesResponse:
    latest_map = await exchange_rate_repository.get_latest_all(session)
    rates = [ExchangeRateResponse.model_validate(r) for r in latest_map.values()]
    last_update = max((r.date for r in rates), default=None)
    return LatestRatesResponse(rates=rates, last_update=last_update)


# Returns all rates for a specific date.
async def get_rates_by_date(
    session: AsyncSession,
    rate_date: date_type,
) -> list[ExchangeRateResponse]:
    rates = await exchange_rate_repository.get_by_date(session, rate_date)
    return [ExchangeRateResponse.model_validate(r) for r in rates]


# Returns, per pair, how many rates are stored and the first and last date. Read by the backfill command.
async def get_coverage_by_pair(session: AsyncSession) -> dict[ExchangeRatePair, tuple[int, date_type, date_type]]:
    return await exchange_rate_repository.get_coverage_by_pair(session)


# Returns every stored rate grouped by pair (sorted by date ascending), serving a cached copy for
# up to RATES_CACHE_TTL_SECONDS. No single-flight: concurrent misses each load once (harmless).
# Returns the cached dict itself — callers must treat it as read-only.
async def get_rates_grouped_by_pair_cached(session: AsyncSession) -> dict[ExchangeRatePair, list[RatePoint]]:
    global _rates_cache, _rates_cache_loaded_at
    now = time.monotonic()
    if _rates_cache is not None and _rates_cache_loaded_at is not None and now - _rates_cache_loaded_at < RATES_CACHE_TTL_SECONDS:
        return _rates_cache
    _rates_cache = await exchange_rate_repository.get_all_grouped_by_pair(session)
    _rates_cache_loaded_at = now
    return _rates_cache


# Drops the cached rates so the next lookup reloads. Called right after the scheduler stores fresh
# rates; any other process (multi-worker deploys) falls back to the TTL bound.
def invalidate_rates_cache() -> None:
    global _rates_cache, _rates_cache_loaded_at
    _rates_cache = None
    _rates_cache_loaded_at = None


# Returns the currency codes with exchange-rate support, from the domain registry (the single
# source of truth). No DB access — entry forms build their currency picker from this.
def get_supported_currencies() -> SupportedCurrenciesResponse:
    return SupportedCurrenciesResponse(currencies=sorted(SUPPORTED_CURRENCIES))


# Builds a RateLookup pre-loaded with every stored exchange rate. One DB round-trip;
# callers reuse the returned object across many per-row lookups within a request.
async def build_rate_lookup(
    session: AsyncSession,
    dollar_preference: str | None = None,
) -> RateLookup:
    rates_by_pair = await get_rates_grouped_by_pair_cached(session)
    return RateLookup(dollar_preference, rates_by_pair)


# Builds the per-request RateLookup honoring the user's dollar-rate preference. The single
# entry point converting services use; build ONE per request and pass it down to composed
# service calls so the rates table is never loaded twice for the same request.
async def get_user_rate_lookup(session: AsyncSession, user_id: int) -> RateLookup:
    dollar_preference = await settings_service.get_dollar_pref(session, user_id)
    return await build_rate_lookup(session, dollar_preference)


# Fetches latest rates from all registered providers in parallel and stores each under the date its
# source quotes it for (a Friday quote read on Sunday stays Friday's). A later quote for the same date
# replaces the earlier one. A weekend quote equal to the rate already in force before it is not stored:
# DolarApi re-stamps an unchanged quote on Saturdays and Sundays, and a copy would invent a row (the
# history fill drops the same repeats). The database is read only after the network fetches, so no
# admin connection sits idle while they run. Returns the number of quotes stored.
async def fetch_and_store_latest(session: AsyncSession) -> int:
    # Fetch from all providers in parallel.
    fetch_results = await asyncio.gather(
        *[provider.fetch() for provider in EXCHANGE_RATE_PROVIDERS],
        return_exceptions=True,
    )

    rows: list[ExchangeRateRow] = []
    for provider, results in zip(EXCHANGE_RATE_PROVIDERS, fetch_results):
        if isinstance(results, BaseException):
            logger.exception("Provider %s failed: %s.", provider.source, results)
            continue
        for quote in results:
            rows.append(ExchangeRateRow(quote.quote_date, quote.pair, quote.rate, provider.source))

    rows = await _drop_weekend_repeats(session, rows)
    if not rows:
        await session.commit()
        return 0

    await exchange_rate_repository.bulk_upsert(session, rows)
    await session.commit()

    # Fresh rates just landed — serve them immediately instead of waiting out the TTL.
    invalidate_rates_cache()

    logger.info("Stored %d exchange rates (quote dates %s).", len(rows), sorted({row.date.isoformat() for row in rows}))
    return len(rows)


# Days read back from a weekend quote's date to find the rate in force before it (a long weekend plus
# holidays fits inside it).
_WEEKEND_LOOKBACK_DAYS = 7


# Drops each weekend row whose rate equals the rate stored for the latest earlier date of its pair —
# a repeat lookups already carry forward. A weekend row that differs (a late Friday close) is kept.
async def _drop_weekend_repeats(session: AsyncSession, rows: list[ExchangeRateRow]) -> list[ExchangeRateRow]:
    weekend_dates = [row.date for row in rows if row.date.weekday() >= 5]
    if not weekend_dates:
        return rows
    stored = await exchange_rate_repository.get_by_date_range(
        session, min(weekend_dates) - timedelta(days=_WEEKEND_LOOKBACK_DAYS), max(weekend_dates) - timedelta(days=1)
    )
    kept: list[ExchangeRateRow] = []
    for row in rows:
        if row.date.weekday() >= 5:
            earlier = [r for r in stored if r.pair == row.pair and r.date < row.date]
            previous = max(earlier, key=lambda r: r.date) if earlier else None
            if previous is not None and quantize(Decimal(previous.rate), _RATE_QUANTUM) == quantize(row.rate, _RATE_QUANTUM):
                continue
        kept.append(row)
    return kept


# What a history run would write (or wrote) for one pair.
class PairBackfillCounts(NamedTuple):
    inserted: int
    repaired: int


# The weekdays in [start, end] each pair has no stored rate for. Weekends are never expected (lookups
# carry Friday's rate over them). Only pairs with at least one missing weekday appear.
def find_missing_weekdays(
    stored_dates: dict[ExchangeRatePair, set[date_type]],
    pairs: Sequence[ExchangeRatePair],
    start: date_type,
    end: date_type,
) -> dict[ExchangeRatePair, list[date_type]]:
    weekdays: list[date_type] = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            weekdays.append(day)
        day += timedelta(days=1)
    missing: dict[ExchangeRatePair, list[date_type]] = {}
    for pair in pairs:
        dates = stored_dates.get(pair, set())
        gaps = [d for d in weekdays if d not in dates]
        if gaps:
            missing[pair] = gaps
    return missing


# A stored row is a PROVABLY misdated quote — and the only kind of existing row a history run replaces —
# when all of these hold: a latest provider stored it (only they stamped the server's date); the history
# source has its own, DIFFERENT quote for that same date; and the stored rate is exactly the quote in
# force BEFORE that date. That is a quote carried onto a later day, not a reading of that day. Any other
# disagreement (an intraday reading, a manual rate) is not provable and the row is kept.
def is_misdated(row: ExchangeRate, quote_rate: Decimal, previous_rate: Decimal | None) -> bool:
    if row.source not in LATEST_SOURCES or previous_rate is None:
        return False
    stored = quantize(Decimal(row.rate), _RATE_QUANTUM)
    return stored != quote_rate and stored == previous_rate


# Splits a history provider's quotes into the rows to insert (no row stored for that date and pair) and
# the rows to repair (stored but provably misdated), keeping only quotes dated in [start, end]. Quotes
# before `start` only tell which rate was in force on the first days. Pure: no DB, no network.
def plan_history_writes(
    quotes: list[ExchangeRateQuote],
    source: str,
    existing: dict[tuple[date_type, ExchangeRatePair], ExchangeRate],
    start: date_type,
    end: date_type,
) -> tuple[list[ExchangeRateRow], list[ExchangeRateRow]]:
    by_pair: dict[ExchangeRatePair, list[ExchangeRateQuote]] = {}
    for quote in quotes:
        by_pair.setdefault(quote.pair, []).append(quote)

    inserts: list[ExchangeRateRow] = []
    repairs: list[ExchangeRateRow] = []
    for pair, pair_quotes in by_pair.items():
        previous_rate: Decimal | None = None
        for quote in sorted(pair_quotes, key=lambda q: q.quote_date):
            rate = quantize(quote.rate, _RATE_QUANTUM)
            if start <= quote.quote_date <= end:
                row = existing.get((quote.quote_date, pair))
                if row is None:
                    inserts.append(ExchangeRateRow(quote.quote_date, pair, rate, source))
                elif is_misdated(row, rate, previous_rate):
                    repairs.append(ExchangeRateRow(quote.quote_date, pair, rate, source))
            previous_rate = rate
    return inserts, repairs


# Fetches one history provider's quotes for `pairs` in [start, end], plus the context days before it.
# Raises ExchangeRateHistoryUnavailable.
async def _fetch_provider_history(
    provider: ExchangeRateHistoryProviderInfo,
    pairs: tuple[ExchangeRatePair, ...],
    start: date_type,
    end: date_type,
) -> list[ExchangeRateQuote]:
    return await provider.fetch(start - timedelta(days=HISTORY_CONTEXT_DAYS), end, pairs)


# Writes planned history rows in one transaction: inserts never touch a stored row, repairs replace the
# provably misdated ones. Returns the number of rows actually inserted.
async def _apply_history_writes(
    session: AsyncSession,
    inserts: list[ExchangeRateRow],
    repairs: list[ExchangeRateRow],
) -> int:
    if not inserts and not repairs:
        return 0
    inserted = await exchange_rate_repository.bulk_insert_missing(session, inserts)
    if repairs:
        await exchange_rate_repository.bulk_upsert(session, repairs)
    await session.commit()
    invalidate_rates_cache()
    return inserted


# Loads the stored rows dated in [start, end], keyed by (date, pair).
async def _load_existing(
    session: AsyncSession,
    start: date_type,
    end: date_type,
) -> dict[tuple[date_type, ExchangeRatePair], ExchangeRate]:
    rows = await exchange_rate_repository.get_by_date_range(session, start, end)
    return {(row.date, row.pair): row for row in rows}


# Counts planned rows per pair.
def _count_by_pair(
    inserts: list[ExchangeRateRow],
    repairs: list[ExchangeRateRow],
) -> dict[ExchangeRatePair, PairBackfillCounts]:
    counts: dict[ExchangeRatePair, PairBackfillCounts] = {}
    for pair in {row.pair for row in inserts} | {row.pair for row in repairs}:
        counts[pair] = PairBackfillCounts(
            inserted=sum(1 for row in inserts if row.pair == pair),
            repaired=sum(1 for row in repairs if row.pair == pair),
        )
    return counts


# Fills every pair's history in [start, end] from the history providers: inserts each day the source
# quotes that has no stored row, and replaces a stored row only when it is provably misdated (see
# is_misdated). Idempotent: a second run over the same range writes nothing. A provider that cannot
# answer raises ExchangeRateHistoryUnavailable and nothing is written. With dry_run, plans and reports
# without writing. Returns the counts per pair.
async def backfill_history(
    session: AsyncSession,
    start: date_type,
    end: date_type,
    *,
    dry_run: bool = False,
) -> dict[ExchangeRatePair, PairBackfillCounts]:
    # Network first, database after: no connection is held while the sources answer.
    fetched = await asyncio.gather(*[_fetch_provider_history(provider, provider.pairs, start, end) for provider in EXCHANGE_RATE_HISTORY_PROVIDERS])
    existing = await _load_existing(session, start, end)
    inserts: list[ExchangeRateRow] = []
    repairs: list[ExchangeRateRow] = []
    for provider, quotes in zip(EXCHANGE_RATE_HISTORY_PROVIDERS, fetched):
        provider_inserts, provider_repairs = plan_history_writes(quotes, provider.source, existing, start, end)
        inserts.extend(provider_inserts)
        repairs.extend(provider_repairs)
    if not dry_run:
        await _apply_history_writes(session, inserts, repairs)
    return _count_by_pair(inserts, repairs)


# The scheduled gap check: finds the weekdays in the last GAP_FILL_WINDOW_DAYS (up to yesterday; today
# belongs to the latest fetch) that a pair has no rate for, and fills them from the history providers.
# Fetches only from a provider with a missing pair, only for those pairs, from the first missing day.
# A provider that cannot answer is logged and skipped; the next run tries again. Weekdays the source
# itself has no quote for (an ECB holiday) stay missing and are simply asked for again next run — one
# small request, no row invented. The read that finds the gaps is committed before any network call,
# so its admin connection goes back to the pool while the sources answer; the rows are read again after
# the fetch to plan against. Returns the number of rows inserted.
async def fill_recent_gaps(session: AsyncSession, today: date_type | None = None) -> int:
    today = today or date_type.today()
    end = today - timedelta(days=1)
    start = today - timedelta(days=GAP_FILL_WINDOW_DAYS)
    stored_dates: dict[ExchangeRatePair, set[date_type]] = {}
    for rate_date, pair in await _load_existing(session, start, end):
        stored_dates.setdefault(pair, set()).add(rate_date)
    await session.commit()
    missing = find_missing_weekdays(stored_dates, list(ExchangeRatePair), start, end)
    if not missing:
        return 0

    fetched: list[tuple[ExchangeRateHistoryProviderInfo, date_type, list[ExchangeRateQuote]]] = []
    for provider in EXCHANGE_RATE_HISTORY_PROVIDERS:
        gap_pairs = tuple(pair for pair in provider.pairs if pair in missing)
        if not gap_pairs:
            continue
        first_missing = min(missing[pair][0] for pair in gap_pairs)
        try:
            quotes = await _fetch_provider_history(provider, gap_pairs, first_missing, end)
        except ExchangeRateHistoryUnavailable as exc:
            logger.warning("Exchange-rate gap fill: %s did not answer (%s); retrying next run.", provider.source, exc)
            continue
        fetched.append((provider, first_missing, quotes))
    if not fetched:
        return 0

    existing = await _load_existing(session, min(first for _p, first, _q in fetched), end)
    inserts: list[ExchangeRateRow] = []
    repairs: list[ExchangeRateRow] = []
    for provider, first_missing, quotes in fetched:
        provider_inserts, provider_repairs = plan_history_writes(quotes, provider.source, existing, first_missing, end)
        inserts.extend(provider_inserts)
        repairs.extend(provider_repairs)

    inserted = await _apply_history_writes(session, inserts, repairs)
    if inserted or repairs:
        logger.info("Exchange-rate gap fill: %d rows inserted, %d misdated rows repaired.", inserted, len(repairs))
    return inserted
