import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.exchange_rate import ExchangeRatePair
from app.repositories.exchange_rate_repository import ExchangeRateRow, exchange_rate_repository

# The two statements the exchange-rate history is written with, whose whole contract lives in the SQL:
#
#   * bulk_insert_missing — ON CONFLICT (date, pair) DO NOTHING. It must leave an existing row exactly as
#     it was (a DO UPDATE here would silently overwrite every stored rate with the history source's), and
#     report only the rows it actually inserted, so a second run reads as zero;
#   * bulk_upsert — each row under ITS OWN date (the latest fetch now stores quotes from different days in
#     one statement), replacing the rate and source of a row already there.
#
# The unit suite's in-memory repository assumes both; this holds the real statements to them. The table
# is global, so the rows live in 1990, before any real rate, and are removed before and after. Admin role
# (renly_admin, BYPASSRLS), as the scheduler and the backfill command write.

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_DAY_1 = date(1990, 3, 1)
_DAY_2 = date(1990, 3, 2)
_MEP = ExchangeRatePair.USD_ARS_MEP
_EUR = ExchangeRatePair.USD_EUR


# A session factory on the admin role, with this file's 1990 rows removed before and after.
@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    clean = text("DELETE FROM exchange_rates WHERE date BETWEEN '1990-01-01' AND '1990-12-31'")
    async with maker() as s:
        await s.execute(clean)
        await s.commit()
    yield maker
    async with maker() as s:
        await s.execute(clean)
        await s.commit()
    await engine.dispose()


# The 1990 rows as {(date, pair): (rate, source)}.
async def _rows(maker) -> dict:
    async with maker() as s:
        result = await s.execute(text("SELECT date, pair, rate, source FROM exchange_rates WHERE date BETWEEN '1990-01-01' AND '1990-12-31'"))
        return {(d, ExchangeRatePair(p)): (rate, source) for d, p, rate, source in result.all()}


class TestInsertMissingNeverOverwrites:
    @pytest.mark.asyncio
    async def test_an_existing_row_is_left_as_it_was_and_not_counted(self, factory):
        async with factory() as s:
            await exchange_rate_repository.bulk_upsert(s, [ExchangeRateRow(_DAY_1, _MEP, Decimal("12.5"), "manual")])
            await s.commit()

        async with factory() as s:
            inserted = await exchange_rate_repository.bulk_insert_missing(
                s,
                [
                    ExchangeRateRow(_DAY_1, _MEP, Decimal("99"), "argentinadatos"),
                    ExchangeRateRow(_DAY_2, _MEP, Decimal("13"), "argentinadatos"),
                ],
            )
            await s.commit()

        assert inserted == 1
        assert await _rows(factory) == {
            (_DAY_1, _MEP): (Decimal("12.500000"), "manual"),
            (_DAY_2, _MEP): (Decimal("13.000000"), "argentinadatos"),
        }

    @pytest.mark.asyncio
    async def test_a_second_insert_of_the_same_rows_inserts_nothing(self, factory):
        rows = [ExchangeRateRow(_DAY_1, _EUR, Decimal("0.9"), "frankfurter"), ExchangeRateRow(_DAY_2, _EUR, Decimal("0.91"), "frankfurter")]
        async with factory() as s:
            first = await exchange_rate_repository.bulk_insert_missing(s, rows)
            await s.commit()
        async with factory() as s:
            second = await exchange_rate_repository.bulk_insert_missing(s, rows)
            await s.commit()

        assert (first, second) == (2, 0)
        assert len(await _rows(factory)) == 2


class TestUpsertWritesEachRowUnderItsOwnDate:
    @pytest.mark.asyncio
    async def test_rows_of_different_days_land_on_their_days_and_replace_what_was_there(self, factory):
        async with factory() as s:
            await exchange_rate_repository.bulk_insert_missing(s, [ExchangeRateRow(_DAY_1, _MEP, Decimal("10"), "dolarapi")])
            await s.commit()

        async with factory() as s:
            await exchange_rate_repository.bulk_upsert(
                s,
                [
                    ExchangeRateRow(_DAY_1, _MEP, Decimal("11"), "argentinadatos"),
                    ExchangeRateRow(_DAY_2, _EUR, Decimal("0.9"), "frankfurter"),
                ],
            )
            await s.commit()

        assert await _rows(factory) == {
            (_DAY_1, _MEP): (Decimal("11.000000"), "argentinadatos"),
            (_DAY_2, _EUR): (Decimal("0.900000"), "frankfurter"),
        }
