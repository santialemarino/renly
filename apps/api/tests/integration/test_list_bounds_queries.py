import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# SEC-11's two bounds against a real database, because neither survives a mocked session: a stub
# repository returns whatever list it was handed, so a LIMIT that never reached the SQL and one that
# did are indistinguishable from a unit test.
#
# Both suites here seed PAST the boundary, which is the point. A cap of 500 asserted against twelve
# rows passes with the cap deleted, and a page-2 assertion against a single page of data passes with
# the OFFSET deleted — a fixture that happens to satisfy a rule is not a test of it. So the cap is
# driven with MAX_LIST_ROWS + 1 rows and the pager with three pages' worth.
#
# Owner role, no RLS involved: this is about how much a query returns, not about who may see it.
from app.repositories import collection_repository, transaction_repository
from app.utils.pagination import MAX_LIST_ROWS

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "list_bounds@test.local"

# One more than the ceiling, so the ceiling is the only reason a row is missing.
_OVER_THE_CAP = MAX_LIST_ROWS + 1

# Two and a bit pages at the default size, so page 2 is a middle page (bounded on both sides) rather
# than the last one — a last page is also what an unapplied LIMIT returns.
_PAGE_SIZE = 10
_TRANSACTIONS = 25


# Seeds one user with MAX_LIST_ROWS + 1 collections and one investment carrying _TRANSACTIONS rows, all
# dated the SAME day so the id tiebreak is the only thing making the page order total.
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('bounds', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        await s.execute(
            text("INSERT INTO investment_collections (user_id, name) SELECT :u, 'bounds_' || lpad(i::text, 4, '0') FROM generate_series(1, :n) AS i"),
            {"u": user, "n": _OVER_THE_CAP},
        )
        investment = (
            await s.execute(
                text(
                    "INSERT INTO investments (user_id, created_by, name, category, base_currency) "
                    "VALUES (:u, :u, 'bounds_inv', 'stocks', 'USD') RETURNING id"
                ),
                {"u": user},
            )
        ).scalar_one()
        # Every row on one date, and each carrying a DISTINCT amount — the amount is what the content
        # assertion reads, so a page holding the right ids but the wrong rows is visible.
        await s.execute(
            text(
                "INSERT INTO transactions (investment_id, user_id, date, amount, currency, type) "
                "SELECT :i, :u, '2026-03-01', i, 'USD', 'buy' FROM generate_series(1, :n) AS i"
            ),
            {"i": investment, "u": user, "n": _TRANSACTIONS},
        )
        await s.commit()
    yield {"user": user, "investment": investment, "maker": maker}
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM transactions WHERE investment_id IN (SELECT id FROM investments WHERE name = 'bounds_inv')"))
    await s.execute(text("DELETE FROM investments WHERE name = 'bounds_inv'"))
    await s.execute(text("DELETE FROM investment_collections WHERE name LIKE 'bounds\\_%'"))
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


class TestTheCapBites:
    @pytest.mark.asyncio
    async def test_a_capped_list_stops_at_the_ceiling(self, seeded):
        # The assertion the cap exists for, and it can only be made past the boundary: the dev database
        # has three collections, against which this passes with the LIMIT deleted.
        async with seeded["maker"]() as s:
            rows = await collection_repository.list_by_user(s, seeded["user"], limit=MAX_LIST_ROWS)
        assert len(rows) == MAX_LIST_ROWS

    @pytest.mark.asyncio
    async def test_the_same_read_without_a_limit_returns_every_row(self, seeded):
        # The other half, and what makes the one above meaningful: the ceiling is opt-in, so the shared
        # query the dashboard and the payments calendar SUM has to keep returning everything. If this
        # ever starts returning MAX_LIST_ROWS, a net-worth total is silently short.
        async with seeded["maker"]() as s:
            rows = await collection_repository.list_by_user(s, seeded["user"])
        assert len(rows) == _OVER_THE_CAP


class TestThePagerPartitions:
    @pytest.mark.asyncio
    async def test_the_total_counts_every_row_rather_than_the_page(self, seeded):
        async with seeded["maker"]() as s:
            rows, total = await transaction_repository.list_by_investment(s, seeded["investment"], page=1, page_size=_PAGE_SIZE)
        assert (len(rows), total) == (_PAGE_SIZE, _TRANSACTIONS)

    @pytest.mark.asyncio
    async def test_the_last_page_holds_the_remainder(self, seeded):
        async with seeded["maker"]() as s:
            rows, _ = await transaction_repository.list_by_investment(s, seeded["investment"], page=3, page_size=_PAGE_SIZE)
        assert len(rows) == _TRANSACTIONS - 2 * _PAGE_SIZE

    @pytest.mark.asyncio
    async def test_a_page_past_the_end_is_empty_rather_than_an_error(self, seeded):
        async with seeded["maker"]() as s:
            rows, total = await transaction_repository.list_by_investment(s, seeded["investment"], page=99, page_size=_PAGE_SIZE)
        assert (rows, total) == ([], _TRANSACTIONS)

    @pytest.mark.asyncio
    async def test_walking_every_page_yields_each_row_exactly_once(self, seeded):
        # The assertion the id tiebreak exists for. Every seeded row shares one date, so ordering by
        # date alone leaves the rest to the planner and a row may repeat on one page and vanish from
        # another. Comparing the WALK against the whole set catches both at once, where a per-page
        # length check would see three pages of the right size and call it correct.
        seen: list[int] = []
        async with seeded["maker"]() as s:
            for page in (1, 2, 3):
                rows, _ = await transaction_repository.list_by_investment(s, seeded["investment"], page=page, page_size=_PAGE_SIZE)
                seen.extend(row.id for row in rows)
            everything, _ = await transaction_repository.list_by_investment(s, seeded["investment"], page=1, page_size=_TRANSACTIONS)
        assert len(seen) == len(set(seen)) == _TRANSACTIONS
        assert seen == [row.id for row in everything]


class TestThePagerSaysWhatEachRowIs:
    # A partition test proves nothing about LABELS: "which page a row lands on" and "what that row
    # says" are two assertions, and the class above only makes the first.

    @pytest.mark.asyncio
    async def test_each_page_carries_the_rows_content_and_not_just_its_place(self, seeded):
        # The seeded amounts run 1..25 and the order is newest-id first, so page 2 must read 15..6 —
        # values, not a count. A repository returning ten rows of the wrong investment, or the right ids
        # paired with another row's amounts, passes every length assertion and fails this one.
        async with seeded["maker"]() as s:
            rows, _ = await transaction_repository.list_by_investment(s, seeded["investment"], page=2, page_size=_PAGE_SIZE)
        assert [int(row.amount) for row in rows] == list(range(15, 5, -1))
        assert {row.investment_id for row in rows} == {seeded["investment"]}
