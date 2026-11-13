import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.domain import InvestmentHasHistoryError
from app.models.user import User
from app.services import investment_service

# Deleting an investment checks for history and then deletes, and its snapshots and transactions go with
# it (ON DELETE CASCADE). Unlocked, a snapshot written between the check and the DELETE was cascaded away
# with no error anywhere. The delete now locks the investment row first; a snapshot insert holds
# FOR KEY SHARE on that row through its foreign key, so the two serialise and the check sees the snapshot.
#
# Only a real Postgres shows it: the race is between two transactions' row locks. Admin role
# (renly_admin, BYPASSRLS): the question is the locking, not the policies.

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "investment_delete_race@test.local"


@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user_id = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('race', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        investment_id = (
            await s.execute(
                text(
                    "INSERT INTO investments (user_id, created_by, name, category, base_currency) "
                    "VALUES (:u, :u, 'race', 'stocks', 'USD') RETURNING id"
                ),
                {"u": user_id},
            )
        ).scalar_one()
        await s.commit()
    user = User(id=user_id, name="race", email=_EMAIL, password_hash="h", session_epoch=0)
    yield {"maker": maker, "user": user, "investment_id": investment_id}
    async with maker() as s:
        await _cleanup(s)
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
    await s.commit()


@pytest.mark.asyncio
async def test_a_snapshot_written_during_the_delete_stops_it(seeded):
    maker, user, investment_id = seeded["maker"], seeded["user"], seeded["investment_id"]
    async with maker() as writer, maker() as deleter:
        # A snapshot insert in flight: its foreign-key check holds FOR KEY SHARE on the investment.
        await writer.execute(
            text("INSERT INTO investment_snapshots (investment_id, user_id, date, value, currency) VALUES (:i, :u, CURRENT_DATE, 100, 'USD')"),
            {"i": investment_id, "u": user.id},
        )
        delete = asyncio.create_task(investment_service.delete_investment(deleter, investment_id, user))
        await asyncio.sleep(0.5)
        # The delete is waiting on the row lock rather than reading a history that is about to change.
        assert not delete.done()
        await writer.commit()
        with pytest.raises(InvestmentHasHistoryError):
            await delete
        await deleter.rollback()

    async with maker() as s:
        snapshots = (await s.execute(text("SELECT count(*) FROM investment_snapshots WHERE investment_id = :i"), {"i": investment_id})).scalar_one()
        investments = (await s.execute(text("SELECT count(*) FROM investments WHERE id = :i"), {"i": investment_id})).scalar_one()
    assert (investments, snapshots) == (1, 1)
