import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Two snapshot queries whose correctness lives entirely in the SQL, where a mocked session cannot
# reach it — both were mutated in a sweep and both went undetected by every unit test in the suite.
#
#   * get_latest_by_investments bounds its MAX by as_of_date. Filtering after the aggregate instead
#     would DROP an investment whose latest snapshot is newer than the date, rather than returning
#     its value on that date — which understates a historical NAV and misprices every back-dated
#     ownership event issued against it. The difference is invisible to a stub, which returns
#     whatever it was told either way.
#   * bulk_upsert writes pot_id. Omitting it produces a row with neither owner, which only the
#     database's single-owner CHECK will tell you about.
#
# Owner role, no RLS involved — this is about query semantics, not visibility.
from app.models.snapshot import InvestmentSnapshot
from app.repositories import snapshot_repository

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "snapshot_scope@test.local"


# Seeds one user with a private investment carrying three snapshots, plus a group/pot with a co-owned
# investment, then tears the lot down. Ordering on teardown matters: every pot_id FK is RESTRICT.
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('snap', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        private = (
            await s.execute(
                text(
                    "INSERT INTO investments (user_id, created_by, name, category, base_currency) "
                    "VALUES (:u, :u, 'snap_private', 'stocks', 'USD') RETURNING id"
                ),
                {"u": user},
            )
        ).scalar_one()
        for d, v in ((date(2026, 1, 1), 100), (date(2026, 3, 1), 150), (date(2026, 9, 1), 900)):
            await s.execute(
                text("INSERT INTO investment_snapshots (investment_id, user_id, date, value, currency) VALUES (:i, :u, :d, :v, 'USD')"),
                {"i": private, "u": user, "d": d, "v": v},
            )
        group = (
            await s.execute(text("INSERT INTO groups (name, kind, created_by) VALUES ('snap_group', 'household', :u) RETURNING id"), {"u": user})
        ).scalar_one()
        pot = (
            await s.execute(text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"), {"g": group})
        ).scalar_one()
        shared = (
            await s.execute(
                text(
                    "INSERT INTO investments (pot_id, created_by, name, category, base_currency) "
                    "VALUES (:p, :u, 'snap_shared', 'stocks', 'USD') RETURNING id"
                ),
                {"p": pot, "u": user},
            )
        ).scalar_one()
        await s.commit()
    yield {"private": private, "shared": shared, "pot": pot, "user": user, "maker": maker}
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM investment_snapshots WHERE investment_id IN (SELECT id FROM investments WHERE name LIKE 'snap_%')"))
    await s.execute(text("DELETE FROM investments WHERE name LIKE 'snap_%'"))
    await s.execute(text("DELETE FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = 'snap_group')"))
    await s.execute(text("DELETE FROM groups WHERE name = 'snap_group'"))
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


class TestTheValuationDateBound:
    @pytest.mark.asyncio
    async def test_a_past_date_returns_the_latest_snapshot_on_or_before_it(self, seeded):
        # 150 (2026-03-01), NOT 900 (2026-09-01) and NOT nothing at all. Filtering after the MAX
        # would return nothing here, because the unbounded MAX is the September row.
        async with seeded["maker"]() as s:
            found = await snapshot_repository.get_latest_by_investments(s, [seeded["private"]], as_of_date=date(2026, 6, 1))
        assert found[seeded["private"]].value == Decimal("150.00")

    @pytest.mark.asyncio
    async def test_no_date_still_returns_the_genuinely_latest(self, seeded):
        # The positive control, and the behaviour every existing caller depends on.
        async with seeded["maker"]() as s:
            found = await snapshot_repository.get_latest_by_investments(s, [seeded["private"]])
        assert found[seeded["private"]].value == Decimal("900.00")

    @pytest.mark.asyncio
    async def test_a_date_before_every_snapshot_returns_nothing_rather_than_the_earliest(self, seeded):
        async with seeded["maker"]() as s:
            found = await snapshot_repository.get_latest_by_investments(s, [seeded["private"]], as_of_date=date(2025, 1, 1))
        assert found == {}


class TestBulkUpsertCarriesTheScope:
    @pytest.mark.asyncio
    async def test_a_co_owned_investments_snapshot_survives_the_single_owner_check(self, seeded):
        # Dropping pot_id from the values dict produces a row with NEITHER owner, which only the
        # database rejects — every unit test in the suite passes either way.
        async with seeded["maker"]() as s:
            await snapshot_repository.bulk_upsert(
                s,
                [
                    InvestmentSnapshot(
                        investment_id=seeded["shared"],
                        user_id=None,
                        pot_id=seeded["pot"],
                        date=date(2026, 5, 1),
                        value=Decimal("42.00"),
                        currency="USD",
                        source="manual",
                    )
                ],
            )
            await s.commit()
            row = (
                await s.execute(text("SELECT user_id, pot_id, value FROM investment_snapshots WHERE investment_id = :i"), {"i": seeded["shared"]})
            ).one()
        assert (row[0], row[1], row[2]) == (None, seeded["pot"], Decimal("42.00"))

    @pytest.mark.asyncio
    async def test_a_private_investments_snapshot_is_unchanged_by_the_addition(self, seeded):
        async with seeded["maker"]() as s:
            await snapshot_repository.bulk_upsert(
                s,
                [
                    InvestmentSnapshot(
                        investment_id=seeded["private"],
                        user_id=seeded["user"],
                        pot_id=None,
                        date=date(2026, 5, 1),
                        value=Decimal("7.00"),
                        currency="USD",
                        source="manual",
                    )
                ],
            )
            await s.commit()
            row = (
                await s.execute(
                    text("SELECT user_id, pot_id FROM investment_snapshots WHERE investment_id = :i AND date = '2026-05-01'"),
                    {"i": seeded["private"]},
                )
            ).one()
        assert (row[0], row[1]) == (seeded["user"], None)
