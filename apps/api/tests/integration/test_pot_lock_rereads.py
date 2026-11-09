import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The pot lock re-reads the pot it locks.
#
# Every ledger write loads the pot, then takes its row lock, then prices against it — and the lock can
# wait for another writer. If that writer changed the pot itself (its dollar rate, which every unit price
# converts at) the copy loaded before the lock is stale, and a contribution, buy-out or take-out would be
# priced at a rate that no longer applies. Only a real Postgres shows it: a mocked session has no
# identity map to go stale.
#
# Admin role (renly_admin, BYPASSRLS), no RLS involved: this is about what the session holds after the lock.
from app.models.exchange_rate import DollarRate
from app.models.pot import Pot
from app.repositories import pot_repository

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "pot_lock_rereads@test.local"


@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('lock', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        group = (
            await s.execute(text("INSERT INTO groups (name, kind, created_by) VALUES ('lock_group', 'household', :u) RETURNING id"), {"u": user})
        ).scalar_one()
        pot = (
            await s.execute(text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"), {"g": group})
        ).scalar_one()
        await s.commit()
    yield {"maker": maker, "pot_id": pot}
    async with maker() as s:
        await _cleanup(s)
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM groups WHERE created_by IN (SELECT id FROM users WHERE email = :e)"), {"e": _EMAIL})
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
    await s.commit()


@pytest.mark.asyncio
async def test_the_lock_hands_back_the_pot_as_it_is_once_locked(seeded):
    maker, pot_id = seeded["maker"], seeded["pot_id"]
    async with maker() as writer:
        pot = await writer.get(Pot, pot_id)
        assert pot.dollar_rate == DollarRate.mep
        # Another transaction changes the rate and commits between this one's load and its lock.
        async with maker() as other:
            await other.execute(text("UPDATE pots SET dollar_rate = 'blue' WHERE id = :p"), {"p": pot_id})
            await other.commit()
        await pot_repository.lock(writer, pot_id)
        assert pot.dollar_rate == DollarRate.blue
        await writer.rollback()
