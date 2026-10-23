import os
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The startup catch-up for the month-end auto-snapshot runs only when the month-end tick left nothing
# behind, and "left nothing behind" is one SQL probe: an AUTO snapshot dated ON OR AFTER the month-end.
# The unit tests fake that probe, so both of its predicates were free to change: a strict `>` misses the
# snapshots the tick itself writes — they are dated the month-end — and runs a second batch after every
# restart in the window; dropping the source filter lets any manual valuation entered since stand in for
# a run that never happened, and the month goes without one.
#
# The probe is global by design (the job runs for every user at once), so the fixture lives in 2091,
# where nothing else in a shared test database has a snapshot, and the batch itself is recorded rather
# than run: it would value every ticker-linked holding in the database. Admin role (renly_admin,
# BYPASSRLS), as the scheduler runs.
from app.services import auto_snapshot_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "u25snap_owner@test.local"
_MONTH_END = date(2091, 6, 30)
# A restart the morning after that month-end's 23:00 tick, inside the three-day window.
_RESTART = datetime(2091, 7, 1, 9, 0, tzinfo=UTC)


# A session factory on the admin role, with this file's user (and its cascade) removed before and after.
@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
        await s.commit()
    yield maker
    async with maker() as s:
        await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
        await s.commit()
    await engine.dispose()


# One holding and the given snapshots, as (date, source).
async def _seed(maker, snapshots: list[tuple[date, str]]) -> None:
    async with maker() as s:
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('o', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        investment = (
            await s.execute(
                text(
                    "INSERT INTO investments (user_id, created_by, name, category, base_currency, ticker) "
                    "VALUES (:u, :u, 'u25snap', CAST('stocks' AS investment_category), 'USD', 'U25SNAP') RETURNING id"
                ),
                {"u": user},
            )
        ).scalar_one()
        for on, source in snapshots:
            await s.execute(
                text(
                    "INSERT INTO investment_snapshots (investment_id, user_id, date, value, quantity, currency, source) "
                    "VALUES (:i, :u, :d, 100, 1, 'USD', :s)"
                ),
                {"i": investment, "u": user, "d": on, "s": source},
            )
        await s.commit()


class TestTheCatchUpRunsOnlyWhenTheTickLeftNothing:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("snapshots", "runs"),
        [
            # The tick ran: its snapshots are dated the month-end itself.
            ([(_MONTH_END, "auto")], False),
            # A previous catch-up ran, a day later.
            ([(date(2091, 7, 1), "auto")], False),
            # Only the PREVIOUS day's auto snapshot: the tick did not run.
            ([(date(2091, 6, 29), "auto")], True),
            # Somebody valued the holding by hand after the month-end: still no auto run for the month.
            ([(_MONTH_END, "manual"), (date(2091, 7, 1), "manual")], True),
            ([], True),
        ],
        ids=["tick-ran", "catch-up-ran", "day-before-only", "manual-only", "nothing"],
    )
    async def test_the_probe_decides(self, factory, monkeypatch, snapshots, runs):
        await _seed(factory, snapshots)
        batches = []

        async def recorded(session):
            batches.append(session)
            return 0

        monkeypatch.setattr(auto_snapshot_service, "generate_auto_snapshots", recorded)
        async with factory() as s:
            ran = await auto_snapshot_service.run_startup_catchup(s, catchup_days=3, snapshots_hour_utc=23, now_utc=_RESTART)
        assert ran is runs
        assert len(batches) == (1 if runs else 0)
