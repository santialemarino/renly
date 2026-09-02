# The notification queries whose correctness lives entirely in the SQL, driven against a real database.
#
# Two of them, and each is invisible to a mocked session for its own reason.
#
# The INSERT uses ON CONFLICT DO NOTHING against a PARTIAL unique index, and Postgres matches a partial
# index only when the statement repeats its predicate. Get that wrong and it does not merely misbehave —
# it raises "there is no unique or exclusion constraint matching the ON CONFLICT specification", every
# time, for every event. Which would be invisible: `dispatch` swallows its own exceptions so a push
# outage can never roll back the money write that produced an event, so the failure mode is the whole
# layer silently writing nothing, with a warning in a log nobody reads.
#
# The FEED READS share one WHERE across three statements — the page, the total and the unread count —
# so the failure that matters is the three disagreeing: a badge counting rows the list does not show. A
# unit test can assert the service passes the same exclusion to all three and still not notice that the
# repository ignores it, which is exactly what a mutation sweep found.

import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.notification import Notification, NotificationEvent
from app.repositories import notification_repository

DATABASE_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "notification_dedupe@test.local"


# Seeds one account on the owner role and yields its id plus a session factory, then removes it (the
# notifications cascade with it).
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
        user_id = (
            await s.execute(
                text("INSERT INTO users (name, email, password_hash) VALUES ('D', :e, 'h') RETURNING id"),
                {"e": _EMAIL},
            )
        ).scalar_one()
        await s.commit()
    try:
        yield {"factory": factory, "user_id": user_id}
    finally:
        async with factory() as s:
            await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})
            await s.commit()
        await engine.dispose()


def _rows(user_ids: list[int], *, event=NotificationEvent.snapshot_due, key: str | None = None) -> list[Notification]:
    return [Notification(user_id=user_id, event=event, payload={"group": "Casa"}, dedupe_key=key) for user_id in user_ids]


# The whole point of the arbiter: the same key twice writes once, and the second attempt reports that it
# reached nobody — which is what stops the hourly reminder emailing somebody every hour.
@pytest.mark.asyncio
async def test_the_same_key_is_written_once_and_the_repeat_reaches_nobody(seeded):
    user_id = seeded["user_id"]
    async with seeded["factory"]() as s:
        first = await notification_repository.create_many(s, _rows([user_id], key="pot:1:2026-09"))
        await s.commit()
        second = await notification_repository.create_many(s, _rows([user_id], key="pot:1:2026-09"))
        await s.commit()
        assert first == [user_id]
        assert second == []
        assert (await s.execute(text("SELECT count(*) FROM notifications WHERE user_id = :u"), {"u": user_id})).scalar_one() == 1


# The next period is a different key, so a pot still overdue next month is raised again. Once per
# period, not once ever.
@pytest.mark.asyncio
async def test_a_new_period_is_written(seeded):
    user_id = seeded["user_id"]
    async with seeded["factory"]() as s:
        await notification_repository.create_many(s, _rows([user_id], key="pot:1:2026-09"))
        again = await notification_repository.create_many(s, _rows([user_id], key="pot:1:2026-10"))
        await s.commit()
        assert again == [user_id]


# A one-off notification carries no key and is never deduplicated: two identical shared-expense
# notifications to the same person are two real events, not a repeat.
@pytest.mark.asyncio
async def test_keyless_rows_are_never_deduplicated(seeded):
    user_id = seeded["user_id"]
    async with seeded["factory"]() as s:
        first = await notification_repository.create_many(s, _rows([user_id], event=NotificationEvent.shared_expense_added))
        second = await notification_repository.create_many(s, _rows([user_id], event=NotificationEvent.shared_expense_added))
        await s.commit()
        assert first == [user_id] and second == [user_id]
        count = (await s.execute(text("SELECT count(*) FROM notifications WHERE user_id = :u"), {"u": user_id})).scalar_one()
        assert count == 2


# The dedupe is per (user, event, key), so two people can hold the same key — which is exactly what the
# reminder does: one pot, one period, one key, every writer of that pot.
@pytest.mark.asyncio
async def test_the_same_key_for_two_people_is_two_rows(seeded):
    engine = create_async_engine(DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    second_email = "notification_dedupe_2@test.local"
    try:
        async with factory() as s:
            await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": second_email})
            other = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES ('E', :e, 'h') RETURNING id"),
                    {"e": second_email},
                )
            ).scalar_one()
            await s.commit()
        async with factory() as s:
            written = await notification_repository.create_many(s, _rows([seeded["user_id"], other], key="pot:1:2026-09"))
            await s.commit()
            assert sorted(written) == sorted([seeded["user_id"], other])
    finally:
        async with factory() as s:
            await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": second_email})
            await s.commit()
        await engine.dispose()


# A batch where one row is a repeat and the other is new: the new one still lands. Written as one
# statement, so a naive implementation that gave up on the whole batch at the first conflict would show
# up here and nowhere else.
@pytest.mark.asyncio
async def test_one_repeat_in_a_batch_does_not_lose_the_rest(seeded):
    engine = create_async_engine(DATABASE_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    second_email = "notification_dedupe_3@test.local"
    try:
        async with factory() as s:
            await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": second_email})
            other = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES ('F', :e, 'h') RETURNING id"),
                    {"e": second_email},
                )
            ).scalar_one()
            await s.commit()
        async with factory() as s:
            await notification_repository.create_many(s, _rows([seeded["user_id"]], key="pot:1:2026-09"))
            await s.commit()
            written = await notification_repository.create_many(s, _rows([seeded["user_id"], other], key="pot:1:2026-09"))
            await s.commit()
            assert written == [other]
    finally:
        async with factory() as s:
            await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": second_email})
            await s.commit()
        await engine.dispose()


# --- The feed reads -------------------------------------------------------------------------------


# Seeds a feed of known shape for the read tests: three events, one of them twice, oldest first.
async def _seed_feed(factory, user_id: int) -> None:
    async with factory() as s:
        await notification_repository.create_many(
            s,
            [
                Notification(user_id=user_id, event=NotificationEvent.member_joined, payload={"n": 1}),
                Notification(user_id=user_id, event=NotificationEvent.pot_movement, payload={"n": 2}),
                Notification(user_id=user_id, event=NotificationEvent.pot_movement, payload={"n": 3}),
                Notification(user_id=user_id, event=NotificationEvent.shared_expense_added, payload={"n": 4}),
            ],
        )
        await s.commit()


# The exclusion is applied in SQL, not merely passed to it. Asserted on all three reads together,
# because the three describing different row sets is the actual defect.
@pytest.mark.asyncio
async def test_the_exclusion_reaches_the_page_the_total_and_the_unread_count(seeded):
    user_id = seeded["user_id"]
    await _seed_feed(seeded["factory"], user_id)
    hidden = [NotificationEvent.pot_movement]
    async with seeded["factory"]() as s:
        page = await notification_repository.list_by_user(s, user_id, limit=50, exclude_events=hidden)
        total = await notification_repository.count_by_user(s, user_id, exclude_events=hidden)
        unread = await notification_repository.count_unread(s, user_id, exclude_events=hidden)
    assert [row.event for row in page] == [NotificationEvent.shared_expense_added, NotificationEvent.member_joined]
    assert (total, unread) == (2, 2)


# The positive control for the test above: with nothing excluded, all four come back. Without it, a
# read that returned nothing at all would satisfy every assertion up there.
@pytest.mark.asyncio
async def test_nothing_is_hidden_when_nothing_is_excluded(seeded):
    user_id = seeded["user_id"]
    await _seed_feed(seeded["factory"], user_id)
    async with seeded["factory"]() as s:
        assert len(await notification_repository.list_by_user(s, user_id, limit=50)) == 4
        assert await notification_repository.count_by_user(s, user_id) == 4


# Newest first, and the tie-break is the id — every row here is written in the same transaction, so
# created_at is identical to the microsecond and the ORDER BY's second column is the only thing
# deciding the page. An id-ascending order would put the oldest notification at the top of the feed.
@pytest.mark.asyncio
async def test_the_feed_is_newest_first(seeded):
    user_id = seeded["user_id"]
    await _seed_feed(seeded["factory"], user_id)
    async with seeded["factory"]() as s:
        rows = await notification_repository.list_by_user(s, user_id, limit=50)
    assert [row.payload["n"] for row in rows] == [4, 3, 2, 1]


# Paging walks that order rather than restarting it, which is what makes "show older" show older.
@pytest.mark.asyncio
async def test_paging_continues_the_same_order(seeded):
    user_id = seeded["user_id"]
    await _seed_feed(seeded["factory"], user_id)
    async with seeded["factory"]() as s:
        first = await notification_repository.list_by_user(s, user_id, limit=2)
        second = await notification_repository.list_by_user(s, user_id, limit=2, offset=2)
    assert [row.payload["n"] for row in first] == [4, 3]
    assert [row.payload["n"] for row in second] == [2, 1]


# Mark-all-read takes the same exclusion the reads take, so the button clears exactly what the list was
# showing — and leaves a hidden row unread, ready to be seen when the switch goes back on.
@pytest.mark.asyncio
async def test_mark_all_read_respects_the_same_exclusion(seeded):
    user_id = seeded["user_id"]
    await _seed_feed(seeded["factory"], user_id)
    hidden = [NotificationEvent.pot_movement]
    async with seeded["factory"]() as s:
        updated = await notification_repository.mark_all_read(s, user_id, exclude_events=hidden)
        await s.commit()
        assert updated == 2
        assert await notification_repository.count_unread(s, user_id) == 2
        assert await notification_repository.count_unread(s, user_id, exclude_events=hidden) == 0
