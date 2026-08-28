import os
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The baseline-deletion statement, whose correctness lives entirely in its two WHERE predicates and so
# cannot be reached by a mocked session at all — a stub deletes whatever it was told to.
#
# It is a `DELETE … WHERE`, which the testing skill singles out: a wrong answer REMOVES a row rather
# than merely hiding one. Both predicates carry real weight and each fails differently:
#
#   * `type = 'opening'` — without it, deleting a baseline takes every contribution, withdrawal and
#     re-agreement of that pot with it, wiping history the user never touched.
#   * `pot_id = :p` — without it, deleting one pot's baseline deletes every OTHER pot's too, across
#     every group in the database.
#
# Owner role, no RLS involved: this is about what the statement removes, not about who may call it.
from app.models.pot import OwnershipEventType
from app.repositories import pot_ownership_repository

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "pot_delete@test.local"


# Seeds TWO pots, each with a two-row baseline plus one non-opening event, so a predicate that is too
# wide shows up as a deletion in the other pot or in the same pot's other events.
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('del', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        group = (
            await s.execute(text("INSERT INTO groups (name, kind, created_by) VALUES ('del_group', 'household', :u) RETURNING id"), {"u": user})
        ).scalar_one()
        seats = [
            (
                await s.execute(
                    text(
                        "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) "
                        "VALUES (:g, :u, :n, 'member', TRUE) RETURNING id"
                    ),
                    {"g": group, "u": user if n == "del_a" else None, "n": n},
                )
            ).scalar_one()
            for n in ("del_a", "del_b")
        ]
        pots = [
            (
                await s.execute(
                    text("INSERT INTO pots (group_id, name, base_currency, is_default) VALUES (:g, :n, 'USD', :d) RETURNING id"),
                    {"g": group, "n": n, "d": n == "del_pot_one"},
                )
            ).scalar_one()
            for n in ("del_pot_one", "del_pot_two")
        ]

        async def event(pot: int, kind: str, member: int, units: str) -> int:
            return (
                await s.execute(
                    text(
                        "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price, created_by) "
                        "VALUES (:p, :t, '2026-02-01', :m, :u, 1, :c) RETURNING id"
                    ),
                    {"p": pot, "t": kind, "m": member, "u": units, "c": user},
                )
            ).scalar_one()

        ids = {"maker": maker, "pots": pots}
        for index, pot in enumerate(pots):
            ids[f"opening_a_{index}"] = await event(pot, "opening", seats[0], "60")
            ids[f"opening_b_{index}"] = await event(pot, "opening", seats[1], "40")
            ids[f"contribution_{index}"] = await event(pot, "contribution", seats[0], "5")
        await s.commit()
    yield ids
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM pot_ownership_events WHERE pot_id IN (SELECT id FROM pots WHERE name LIKE 'del_pot_%')"))
    await s.execute(text("DELETE FROM pots WHERE name LIKE 'del_pot_%'"))
    await s.execute(text("DELETE FROM group_members WHERE display_name LIKE 'del_%'"))
    await s.execute(text("DELETE FROM groups WHERE name = 'del_group'"))
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


async def _remaining(s: AsyncSession, pot: int) -> list[tuple[int, str]]:
    rows = await s.execute(text("SELECT id, type::text FROM pot_ownership_events WHERE pot_id = :p ORDER BY id"), {"p": pot})
    return [(row[0], row[1]) for row in rows.all()]


class TestDeleteOpenings:
    @pytest.mark.asyncio
    async def test_it_removes_every_opening_row_of_the_pot(self, seeded):
        async with seeded["maker"]() as s:
            removed = await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            left = await _remaining(s, seeded["pots"][0])
        # Both rows of the baseline, and the count is what the statement actually removed.
        assert removed == 2
        assert [kind for _, kind in left] == ["contribution"]

    @pytest.mark.asyncio
    async def test_it_leaves_every_OTHER_event_of_the_same_pot(self, seeded):
        # Without the `type` predicate this pot's contribution goes too — history the user never touched.
        async with seeded["maker"]() as s:
            await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            left = await _remaining(s, seeded["pots"][0])
        assert left == [(seeded["contribution_0"], "contribution")]

    @pytest.mark.asyncio
    async def test_it_leaves_every_event_of_every_OTHER_pot(self, seeded):
        # Without the `pot_id` predicate this deletes every pot's baseline in the database.
        async with seeded["maker"]() as s:
            await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            left = await _remaining(s, seeded["pots"][1])
        assert [kind for _, kind in left] == ["opening", "opening", "contribution"]

    @pytest.mark.asyncio
    async def test_a_pot_with_no_baseline_removes_nothing_and_says_so(self, seeded):
        # The count is what tells the service an opening was involved, so a no-op must report zero
        # rather than a truthy number.
        async with seeded["maker"]() as s:
            await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            again = await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            left = await _remaining(s, seeded["pots"][0])
        assert again == 0
        assert len(left) == 1

    @pytest.mark.asyncio
    async def test_the_baseline_can_be_recorded_again_afterwards(self, seeded):
        """The whole point of deleting as one act: record_opening refuses while ANY opening row
        survives, so a partial delete left the pot permanently mis-divided with only a re-agreement —
        a gift that never happened — as a way back."""
        async with seeded["maker"]() as s:
            await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            surviving = await pot_ownership_repository.list_by_pot(s, seeded["pots"][0])
        assert not [e for e in surviving if e.type == OwnershipEventType.opening]

    @pytest.mark.asyncio
    async def test_the_units_of_what_remains_are_unchanged(self, seeded):
        # Nothing is stored as a running total, so removing the baseline must not touch another row's
        # figures — it only changes what the replay adds up to.
        async with seeded["maker"]() as s:
            await pot_ownership_repository.delete_openings(s, seeded["pots"][0])
            await s.commit()
            row = (await s.execute(text("SELECT units FROM pot_ownership_events WHERE id = :i"), {"i": seeded["contribution_0"]})).scalar_one()
        assert row == Decimal("5.000000")
