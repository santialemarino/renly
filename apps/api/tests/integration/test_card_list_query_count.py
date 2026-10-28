import os
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.models.user import User
from app.routers import credit_cards as credit_cards_router
from app.services import credit_card_service

# The card list answers, for every card, whether anything still names it (the `has_expenses` flag a
# client reads to offer Archive instead of Delete), and that must cost a FIXED number of statements
# however many cards there are: card_delete_blockers reads each of the five kinds of row that can name a
# card once, for every card at once.
#
# Two halves, each of which the other cannot stand in for:
#
#   * the COUNT, measured as statements on the wire (a cursor listener on the engine) for three users
#     holding 1, 5 and 20 cards, both for the whole list read the route makes and for the blocker read
#     alone. Nothing is assumed about which reads are batched: a per-card read anywhere under the list
#     shows up as a count that moves with N, and one kind read per card as a blocker count past five.
#   * the ANSWER, because a fixed count is easy to buy by answering wrongly: every card but one is named
#     by a different kind of row in turn, and the last is named by nothing.
#
# Admin role (renly_admin, BYPASSRLS): this is about how many statements a read issues and what it
# answers, not about who may see what — every read here filters on its user anyway.

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_PREFIX = "cardlist_"
_CARD_COUNTS = (1, 5, 20)
_ON = date(2026, 3, 10)
# One batch read per kind of row that can name a card (credit_card_service.card_delete_blockers).
_BLOCKER_KINDS = 5


@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    yield engine, maker
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    users = "SELECT id FROM users WHERE email LIKE :p"
    params = {"p": f"{_PREFIX}%"}
    for table in ("expense_entries", "subscriptions", "installments", "payment_obligations"):
        await s.execute(text(f"DELETE FROM {table} WHERE user_id IN ({users})"), params)
    await s.execute(text(f"DELETE FROM credit_cards WHERE user_id IN ({users})"), params)
    await s.execute(text("DELETE FROM users WHERE email LIKE :p"), params)


async def _scalar(s: AsyncSession, sql: str, **params) -> int:
    return (await s.execute(text(sql), params)).scalar_one()


# What names card `index` of a user's cards: the private kinds in turn, and nothing for the last card. A
# group's shared expense is the fifth kind, and needs a group; it is read for every card all the same.
_NAMED_BY = ("expense", "subscription", "installment plan", "payment obligation")


async def _name_card(s: AsyncSession, user: int, card: int, kind: str) -> None:
    if kind == "expense":
        await s.execute(
            text(
                "INSERT INTO expense_entries (user_id, date, amount, currency, payment_method, credit_card_id)"
                " VALUES (:u, :d, 10, 'ARS', 'credit_card', :c)"
            ),
            {"u": user, "d": _ON, "c": card},
        )
    elif kind == "subscription":
        await s.execute(
            text(
                "INSERT INTO subscriptions (user_id, name, amount, currency, billing_cycle, next_billing_date, anchor_day, credit_card_id)"
                " VALUES (:u, :n, 10, 'ARS', 'monthly', :d, :a, :c)"
            ),
            {"u": user, "n": f"{_PREFIX}sub", "d": _ON, "a": _ON.day, "c": card},
        )
    elif kind == "installment plan":
        await s.execute(
            text(
                "INSERT INTO installments (user_id, name, total_amount, installment_amount, currency, installments_count, start_date, credit_card_id)"
                " VALUES (:u, :n, 30, 10, 'ARS', 3, :d, :c)"
            ),
            {"u": user, "n": f"{_PREFIX}plan", "d": _ON, "c": card},
        )
    else:
        await s.execute(
            text(
                "INSERT INTO payment_obligations (user_id, name, amount, currency, next_due_date, anchor_day, credit_card_id)"
                " VALUES (:u, :n, 10, 'ARS', :d, :a, :c)"
            ),
            {"u": user, "n": f"{_PREFIX}bill", "d": _ON, "a": _ON.day, "c": card},
        )


# One user per count, holding that many cards; card i is named by _NAMED_BY[i % 4], except the last,
# which nothing names. Returns {count: (user, {card id: whether something names it})}.
async def _seed(maker) -> dict[int, tuple[User, dict[int, bool]]]:
    seeded = {}
    async with maker() as s:
        for count in _CARD_COUNTS:
            email = f"{_PREFIX}{count}@test.local"
            user_id = await _scalar(s, "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id", n=f"u{count}", e=email)
            named = {}
            for index in range(count):
                card = await _scalar(
                    s,
                    "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, :n, 20, 5, 'ARS') RETURNING id",
                    u=user_id,
                    n=f"{_PREFIX}card {index}",
                )
                is_last = index == count - 1
                if not is_last:
                    await _name_card(s, user_id, card, _NAMED_BY[index % len(_NAMED_BY)])
                named[card] = not is_last
            seeded[count] = (User(id=user_id, name=f"u{count}", email=email, password_hash="h", session_epoch=0), named)
        await s.commit()
    return seeded


# Counts the statements one awaited read sends to the database.
async def _count(engine, read) -> tuple[int, object]:
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        result = await read()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    return len(statements), result


class TestTheCardListCostsAFixedNumberOfStatements:
    @pytest.mark.asyncio
    async def test_the_list_and_its_delete_flags_cost_the_same_at_every_card_count(self, factory):
        engine, maker = factory
        seeded = await _seed(maker)
        route_counts, blocker_counts = {}, {}
        for count, (user, named) in seeded.items():
            card_ids = sorted(named)
            async with maker() as s:
                route_counts[count], cards = await _count(
                    engine,
                    lambda s=s, user=user: credit_cards_router.list_cards(user, s, search=None, sort_by=None, sort_order="asc", show_archived=False),
                )
            async with maker() as s:
                blocker_counts[count], flags = await _count(
                    engine, lambda s=s, user=user, card_ids=card_ids: credit_card_service.cards_have_expenses(s, card_ids, user.id)
                )
            assert {card.id: card.has_expenses for card in cards} == named
            assert flags == named
        print(f"\ncard list statements by card count: {route_counts}; blocker statements: {blocker_counts}")
        assert len(set(route_counts.values())) == 1
        assert set(blocker_counts.values()) == {_BLOCKER_KINDS}
