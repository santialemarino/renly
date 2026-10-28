import json
import os
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.services import notification_service
from app.services import obligation_reminder_service as svc

# The upcoming-bill reminder sends its bills one by one in a fixed order, so a failure that lasts — one
# bill whose dispatch fails on every tick — used to stop every bill after it on every tick. Each bill's
# failure is now its own: rolled back, logged, and re-raised only once the rest were sent, so the job
# still ends failed and the scheduler still reports it at CRITICAL.
#
# On a real session because that is where the two ways of getting it wrong live: a failed statement
# aborts the session's transaction, so without the rollback every later bill fails too; and a rollback
# expires every row the session loaded, so a loop still reading those rows afterwards fails on a lazy
# load an async session cannot make. The failing bill raises a real database error, on the job's own
# session, from inside the dispatch.
#
# Admin role (renly_admin, BYPASSRLS), as the scheduler runs it.

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_PREFIX = "oblisolate_"
# 00:00 UTC is 09:00 in Tokyo, the reminder hour, on a tick where a UTC-fallback user (09:00 UTC) is not
# due — so any other data in the database stays out of it.
_TICK = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)
_DUE = date(2026, 9, 4)
# Three bills, owned by three people, in the order the job sends them. The middle one always fails.
_BILLS = ("first", "broken", "last")


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(DB_URL)
    make = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with make() as s:
        await _cleanup(s)
        await s.commit()
    yield make
    async with make() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    users = "SELECT id FROM users WHERE email LIKE :p"
    params = {"p": f"{_PREFIX}%"}
    await s.execute(text(f"DELETE FROM notifications WHERE user_id IN ({users})"), params)
    await s.execute(text(f"DELETE FROM payment_obligations WHERE user_id IN ({users})"), params)
    await s.execute(text(f"DELETE FROM user_settings WHERE user_id IN ({users})"), params)
    await s.execute(text("DELETE FROM users WHERE email LIKE :p"), params)


# One Tokyo user per bill, each owning one bill due inside the lead time. Returns {bill name: obligation id}.
async def _seed(factory) -> dict[str, int]:
    bills = {}
    async with factory() as s:
        for name in _BILLS:
            user = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"),
                    {"n": name, "e": f"{_PREFIX}{name}@test.local"},
                )
            ).scalar_one()
            await s.execute(
                text("INSERT INTO user_settings (user_id, settings) VALUES (:u, CAST(:s AS jsonb))"),
                {"u": user, "s": json.dumps({"timezone": "Asia/Tokyo"})},
            )
            bills[name] = (
                await s.execute(
                    text(
                        "INSERT INTO payment_obligations (user_id, name, amount, currency, next_due_date, anchor_day, recurrence)"
                        " VALUES (:u, :n, 100, 'ARS', :d, :a, 'monthly') RETURNING id"
                    ),
                    {"u": user, "n": f"{_PREFIX}{name}", "d": _DUE, "a": _DUE.day},
                )
            ).scalar_one()
        await s.commit()
    return bills


class TestOneFailingBillDoesNotSilenceTheRest:
    @pytest.mark.asyncio
    async def test_the_bills_after_a_failing_one_are_still_sent_and_the_job_still_fails(self, factory, monkeypatch, caplog):
        bills = await _seed(factory)
        broken_key = f"obligation:{bills['broken']}:{_DUE.isoformat()}"
        sent = notification_service.dispatch

        # The real dispatch for every bill but the broken one, which fails the way a lasting database
        # error does: a statement on the job's own session that the database refuses.
        async def dispatch(event, user_ids, payload, *, dedupe_key=None, session=None, **kwargs):
            if dedupe_key == broken_key:
                await session.execute(text("SELECT 1 / 0"))
            return await sent(event, user_ids, payload, dedupe_key=dedupe_key, session=session, **kwargs)

        monkeypatch.setattr(svc.notification_service, "dispatch", dispatch)
        async with factory() as session:
            with pytest.raises(DBAPIError, match="division by zero"):
                await svc.send_due_reminders(session, _TICK)

        async with factory() as s:
            told = (
                await s.execute(
                    text("SELECT payload ->> 'obligation_id' FROM notifications WHERE dedupe_key LIKE 'obligation:%' AND payload ->> 'name' LIKE :p"),
                    {"p": f"{_PREFIX}%"},
                )
            ).scalars()
            assert sorted(int(obligation_id) for obligation_id in told) == sorted([bills["first"], bills["last"]])
        assert [r.getMessage() for r in caplog.records if r.levelname == "ERROR"] == [
            f"Obligation reminder for obligation {bills['broken']} failed; sending the rest."
        ]
