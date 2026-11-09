from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.models.exchange_rate import ExchangeRate, ExchangeRatePair
from app.repositories.exchange_rate_repository import ExchangeRateRow
from app.services import exchange_rate_service as svc
from app.services.exchange_rate_providers import (
    ExchangeRateHistoryProviderInfo,
    ExchangeRateHistoryUnavailable,
    ExchangeRateProviderInfo,
    ExchangeRateQuote,
)

# The exchange-rate history: what the scheduled job and the backfill command write, and above all what
# they must NOT write. The rules pinned here:
#
#   * the latest fetch stores each quote under the date its source gives it;
#   * a missing weekday is found and filled from the history providers, and only what is missing is asked for;
#   * a second run over the same range writes nothing (idempotent);
#   * an existing row is never overwritten — except a row PROVABLY misdated: written by a latest
#     provider, holding exactly the quote in force BEFORE its date, where the source quotes that date
#     differently.
#
# The repository is an in-memory fake keyed like the table's UNIQUE (date, pair), whose insert skips a key
# already present, as ON CONFLICT DO NOTHING does; tests/integration/test_exchange_rate_writes.py holds
# the real statements to the same contract. Providers are fakes: no network.

_MEP = ExchangeRatePair.USD_ARS_MEP
_EUR = ExchangeRatePair.USD_EUR

# A Monday, so the window's weekdays are easy to count.
_TODAY = date(2026, 11, 9)


# The table, in memory: (date, pair) -> ExchangeRate.
class _FakeRepository:
    def __init__(self, rows: list[ExchangeRate] | None = None):
        self.rows: dict[tuple[date, ExchangeRatePair], ExchangeRate] = {(r.date, r.pair): r for r in rows or []}
        self.upserts: list[ExchangeRateRow] = []

    async def get_by_date_range(self, session, start, end):
        return [r for (d, _p), r in sorted(self.rows.items()) if start <= d <= end]

    async def bulk_insert_missing(self, session, rows):
        inserted = 0
        for row in rows:
            if (row.date, row.pair) not in self.rows:
                self.rows[(row.date, row.pair)] = ExchangeRate(date=row.date, pair=row.pair, rate=row.rate, source=row.source)
                inserted += 1
        return inserted

    async def bulk_upsert(self, session, rows):
        for row in rows:
            self.upserts.append(row)
            self.rows[(row.date, row.pair)] = ExchangeRate(date=row.date, pair=row.pair, rate=row.rate, source=row.source)
        return len(rows)


class _Session:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


# A history provider answering from `quotes` (filtered to the range and pairs asked for) and recording
# every call; `error` makes it fail instead.
def _history_provider(source, pairs, quotes, calls, error: Exception | None = None) -> ExchangeRateHistoryProviderInfo:
    async def fetch(start, end, wanted):
        calls.append((source, start, end, wanted))
        if error is not None:
            raise error
        return [q for q in quotes if start <= q.quote_date <= end and q.pair in wanted]

    return ExchangeRateHistoryProviderInfo(source, tuple(pairs), fetch)


# Every weekday in [start, end] quoted at `rate`.
def _weekday_quotes(pair, start, end, rate) -> list[ExchangeRateQuote]:
    quotes = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            quotes.append(ExchangeRateQuote(pair, Decimal(rate), day))
        day += timedelta(days=1)
    return quotes


def _row(pair, day, rate, source) -> ExchangeRate:
    return ExchangeRate(date=day, pair=pair, rate=Decimal(rate), source=source)


@pytest.fixture
def repo(monkeypatch):
    fake = _FakeRepository()
    monkeypatch.setattr(svc, "exchange_rate_repository", fake)
    return fake


class TestTheLatestFetchStoresTheQuoteDate:
    # The old fetcher wrote every quote under date.today(); a Friday quote read on Sunday became Sunday's.
    @pytest.mark.asyncio
    async def test_each_quote_is_written_under_its_own_date(self, monkeypatch, repo):
        async def fetch_ars():
            return [ExchangeRateQuote(_MEP, Decimal("1574.05"), date(2026, 11, 6))]

        async def fetch_eur():
            return [ExchangeRateQuote(_EUR, Decimal("0.89566"), date(2026, 11, 5))]

        latest = [ExchangeRateProviderInfo("dolarapi", fetch_ars), ExchangeRateProviderInfo("frankfurter", fetch_eur)]
        monkeypatch.setattr(svc, "EXCHANGE_RATE_PROVIDERS", latest)

        stored = await svc.fetch_and_store_latest(_Session())

        assert stored == 2
        assert sorted(repo.upserts) == sorted(
            [
                ExchangeRateRow(date(2026, 11, 6), _MEP, Decimal("1574.05"), "dolarapi"),
                ExchangeRateRow(date(2026, 11, 5), _EUR, Decimal("0.89566"), "frankfurter"),
            ]
        )


class TestFindMissingWeekdays:
    def test_lists_the_weekdays_without_a_row_and_never_a_weekend(self):
        start, end = date(2026, 11, 2), date(2026, 11, 8)  # Monday to Sunday
        stored = {_MEP: {date(2026, 11, 2), date(2026, 11, 4)}, _EUR: {date(2026, 11, d) for d in range(2, 7)}}

        missing = svc.find_missing_weekdays(stored, [_MEP, _EUR, ExchangeRatePair.USD_GBP], start, end)

        assert missing == {
            _MEP: [date(2026, 11, 3), date(2026, 11, 5), date(2026, 11, 6)],
            ExchangeRatePair.USD_GBP: [date(2026, 11, d) for d in range(2, 7)],
        }


class TestPlanHistoryWrites:
    _START, _END = date(2026, 11, 2), date(2026, 11, 6)

    def _plan(self, quotes, existing_rows):
        existing = {(r.date, r.pair): r for r in existing_rows}
        return svc.plan_history_writes(quotes, "argentinadatos", existing, self._START, self._END)

    def test_inserts_each_quoted_day_with_no_row_and_nothing_outside_the_range(self):
        quotes = _weekday_quotes(_MEP, date(2026, 10, 26), date(2026, 11, 9), "1500")

        inserts, repairs = self._plan(quotes, [_row(_MEP, date(2026, 11, 3), "1500", "dolarapi")])

        assert [r.date for r in inserts] == [date(2026, 11, 2), date(2026, 11, 4), date(2026, 11, 5), date(2026, 11, 6)]
        assert repairs == []

    # A stored rate that disagrees with the source but is NOT the quote of the day before is not provably
    # misdated (an intraday reading, a later correction) and stays.
    def test_keeps_a_differing_row_that_is_not_the_previous_quote(self):
        quotes = [
            ExchangeRateQuote(_MEP, Decimal("1500"), date(2026, 11, 2)),
            ExchangeRateQuote(_MEP, Decimal("1510"), date(2026, 11, 3)),
        ]

        inserts, repairs = self._plan(quotes, [_row(_MEP, date(2026, 11, 3), "1507", "dolarapi")])

        assert repairs == [] and [r.date for r in inserts] == [date(2026, 11, 2)]

    # A manual rate is never replaced, even when it equals the previous quote.
    def test_keeps_a_row_no_latest_provider_wrote(self):
        quotes = [
            ExchangeRateQuote(_MEP, Decimal("1500"), date(2026, 11, 2)),
            ExchangeRateQuote(_MEP, Decimal("1510"), date(2026, 11, 3)),
        ]

        _inserts, repairs = self._plan(quotes, [_row(_MEP, date(2026, 11, 3), "1500", "manual")])

        assert repairs == []

    # The artefact: the old fetcher ran on Tuesday before the market moved and stored Monday's quote
    # (1500) as Tuesday's; the source quotes Tuesday at 1510. That row is replaced.
    def test_repairs_a_latest_row_holding_the_quote_of_the_day_before(self):
        quotes = [
            ExchangeRateQuote(_MEP, Decimal("1500"), date(2026, 11, 2)),
            ExchangeRateQuote(_MEP, Decimal("1510"), date(2026, 11, 3)),
        ]

        _inserts, repairs = self._plan(quotes, [_row(_MEP, date(2026, 11, 3), "1500", "dolarapi")])

        assert repairs == [ExchangeRateRow(date(2026, 11, 3), _MEP, Decimal("1510.000000"), "argentinadatos")]

    # The quote in force before the range's first day comes from the context days fetched before it.
    def test_the_previous_quote_may_come_from_before_the_range(self):
        quotes = [
            ExchangeRateQuote(_MEP, Decimal("1490"), date(2026, 10, 30)),
            ExchangeRateQuote(_MEP, Decimal("1500"), date(2026, 11, 2)),
        ]

        inserts, repairs = self._plan(quotes, [_row(_MEP, date(2026, 11, 2), "1490", "dolarapi")])

        assert inserts == [] and [r.date for r in repairs] == [date(2026, 11, 2)]


class TestFillRecentGaps:
    # Nothing missing in the window: no provider is asked anything.
    @pytest.mark.asyncio
    async def test_asks_nothing_when_no_weekday_is_missing(self, monkeypatch, repo):
        start = _TODAY - timedelta(days=svc.GAP_FILL_WINDOW_DAYS)
        for pair in ExchangeRatePair:
            for q in _weekday_quotes(pair, start, _TODAY - timedelta(days=1), "1"):
                repo.rows[(q.quote_date, pair)] = _row(pair, q.quote_date, "1", "dolarapi")
        calls: list = []
        monkeypatch.setattr(svc, "EXCHANGE_RATE_HISTORY_PROVIDERS", [_history_provider("x", list(ExchangeRatePair), [], calls)])

        assert await svc.fill_recent_gaps(_Session(), today=_TODAY) == 0
        assert calls == []

    # The 44-day outage, in small: MEP has rows up to a Friday and none after; EUR is complete. Only the
    # ARS provider is asked, only for MEP, from the first missing day (plus its context days) to
    # yesterday — never today, which belongs to the latest fetch.
    @pytest.mark.asyncio
    async def test_fills_a_missing_stretch_from_its_first_missing_day(self, monkeypatch, repo):
        start = _TODAY - timedelta(days=svc.GAP_FILL_WINDOW_DAYS)
        yesterday = _TODAY - timedelta(days=1)
        last_stored = date(2026, 10, 2)  # a Friday
        for pair in ExchangeRatePair:
            stop = last_stored if pair == _MEP else yesterday
            for q in _weekday_quotes(pair, start, stop, "1"):
                repo.rows[(q.quote_date, pair)] = _row(pair, q.quote_date, "1", "dolarapi")
        before = len(repo.rows)
        ars_calls: list = []
        eur_calls: list = []
        ars_quotes = _weekday_quotes(_MEP, start, _TODAY, "1")
        monkeypatch.setattr(
            svc,
            "EXCHANGE_RATE_HISTORY_PROVIDERS",
            [
                _history_provider("argentinadatos", [ExchangeRatePair.USD_ARS_OFICIAL, ExchangeRatePair.USD_ARS_BLUE, _MEP], ars_quotes, ars_calls),
                _history_provider("frankfurter", [ExchangeRatePair.USD_BRL, _EUR, ExchangeRatePair.USD_GBP], [], eur_calls),
            ],
        )

        inserted = await svc.fill_recent_gaps(_Session(), today=_TODAY)

        first_missing = date(2026, 10, 5)
        assert ars_calls == [("argentinadatos", first_missing - timedelta(days=svc.HISTORY_CONTEXT_DAYS), yesterday, (_MEP,))]
        assert eur_calls == []
        weekdays_missing = len(_weekday_quotes(_MEP, first_missing, yesterday, "1"))
        assert inserted == weekdays_missing == len(repo.rows) - before
        assert (_TODAY, _MEP) not in repo.rows

    # One provider failing must not cost the other its fill; the failed one is asked again next run.
    @pytest.mark.asyncio
    async def test_a_failing_provider_does_not_block_the_other(self, monkeypatch, repo):
        calls: list = []
        eur_quotes = _weekday_quotes(_EUR, _TODAY - timedelta(days=20), _TODAY, "0.9")
        monkeypatch.setattr(
            svc,
            "EXCHANGE_RATE_HISTORY_PROVIDERS",
            [
                _history_provider("argentinadatos", [_MEP], [], calls, error=ExchangeRateHistoryUnavailable("down")),
                _history_provider("frankfurter", [_EUR], eur_quotes, calls),
            ],
        )

        inserted = await svc.fill_recent_gaps(_Session(), today=_TODAY)

        assert [c[0] for c in calls] == ["argentinadatos", "frankfurter"]
        assert inserted > 0 and {pair for _d, pair in repo.rows} == {_EUR}


class TestBackfillIsIdempotentAndNeverOverwrites:
    _START, _END = date(2026, 10, 1), date(2026, 11, 6)

    def _providers(self, calls):
        mep = _weekday_quotes(_MEP, self._START - timedelta(days=15), self._END, "1500")
        # Tuesday 2026-11-03 moved to 1510.
        mep = [q._replace(rate=Decimal("1510")) if q.quote_date >= date(2026, 11, 3) else q for q in mep]
        eur = _weekday_quotes(_EUR, self._START - timedelta(days=15), self._END, "0.9")
        return [
            _history_provider("argentinadatos", [_MEP], mep, calls),
            _history_provider("frankfurter", [_EUR], eur, calls),
        ]

    @pytest.mark.asyncio
    async def test_a_second_run_writes_nothing(self, monkeypatch, repo):
        monkeypatch.setattr(svc, "EXCHANGE_RATE_HISTORY_PROVIDERS", self._providers([]))
        session = _Session()

        first = await svc.backfill_history(session, self._START, self._END)
        rows_after_first = dict(repo.rows)
        second = await svc.backfill_history(session, self._START, self._END)

        assert sum(c.inserted for c in first.values()) == len(rows_after_first) > 0
        assert second == {}
        assert repo.rows == rows_after_first

    # A manual rate and a differing intraday reading both survive the backfill, unchanged; only the
    # provably misdated row (Monday's 1500 stored as Tuesday's) is replaced.
    @pytest.mark.asyncio
    async def test_existing_rows_survive_except_the_provably_misdated_one(self, monkeypatch, repo):
        manual = _row(_EUR, date(2026, 10, 7), "0.95", "manual")
        intraday = _row(_MEP, date(2026, 10, 8), "1503", "dolarapi")
        misdated = _row(_MEP, date(2026, 11, 3), "1500", "dolarapi")
        for row in (manual, intraday, misdated):
            repo.rows[(row.date, row.pair)] = row
        monkeypatch.setattr(svc, "EXCHANGE_RATE_HISTORY_PROVIDERS", self._providers([]))

        counts = await svc.backfill_history(_Session(), self._START, self._END)

        assert repo.rows[(manual.date, _EUR)] is manual
        assert repo.rows[(intraday.date, _MEP)] is intraday
        assert repo.rows[(misdated.date, _MEP)].rate == Decimal("1510")
        assert counts[_MEP].repaired == 1 and counts[_EUR].repaired == 0

    @pytest.mark.asyncio
    async def test_a_dry_run_writes_nothing(self, monkeypatch, repo):
        monkeypatch.setattr(svc, "EXCHANGE_RATE_HISTORY_PROVIDERS", self._providers([]))
        session = _Session()

        counts = await svc.backfill_history(session, self._START, self._END, dry_run=True)

        assert sum(c.inserted for c in counts.values()) > 0
        assert repo.rows == {} and session.commits == 0
