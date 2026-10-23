import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Two figures a card liability reaches the user through, each read off a real database because the
# balance behind it is SQL — and each with a single operator between the right answer and a wrong one.
#
#   * The net-worth EVOLUTION subtracts the card. Every test that asserted the series before ran with a
#     card balance of zero, where `- card` and `+ card` are the same number, so a flipped sign would have
#     shown a debt as wealth on the chart (and in the overview's month-over-month delta, which is the same
#     series' last two points) with the whole suite green.
#   * The payments calendar bills the statement the due date PAYS. When the closing day and the due day
#     coincide, the statement closes the day it is due and that day's balance is the bill; a strict
#     comparison picks the previous month's statement and shows last month's balance as due.
#
# Admin role (renly_admin, BYPASSRLS): this is about what a read answers, not about who may see it.
from app.models.user import User
from app.services import dashboard_service, exchange_rate_service, payments_calendar_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_PREFIX = "u25card_"
_RATE_SOURCE = "u25card_test"


# A session factory on the admin role, with this file's rows removed before and after.
@pytest_asyncio.fixture
async def factory():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    yield maker
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


# Everything this file writes: the user's rows go with the user on its cascade except the ones naming a
# card, which are removed first; the rate it seeded is tagged by source.
async def _cleanup(s: AsyncSession) -> None:
    users = "SELECT id FROM users WHERE email LIKE :p"
    params = {"p": f"{_PREFIX}%"}
    await s.execute(text(f"DELETE FROM expense_entries WHERE user_id IN ({users})"), params)
    await s.execute(text(f"DELETE FROM credit_cards WHERE user_id IN ({users})"), params)
    await s.execute(text("DELETE FROM users WHERE email LIKE :p"), params)
    await s.execute(text("DELETE FROM exchange_rates WHERE source = :s"), {"s": _RATE_SOURCE})


async def _scalar(s: AsyncSession, sql: str, **params) -> int:
    return (await s.execute(text(sql), params)).scalar_one()


async def _user(s: AsyncSession, tag: str) -> User:
    email = f"{_PREFIX}{tag}@test.local"
    user_id = await _scalar(s, "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id", n=tag, e=email)
    return User(id=user_id, name=tag, email=email, password_hash="h", session_epoch=0)


async def _card(s: AsyncSession, user: int, *, closing_day: int, due_day: int) -> int:
    return await _scalar(
        s,
        "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, :n, :c, :d, 'USD') RETURNING id",
        u=user,
        n=f"{_PREFIX}card",
        c=closing_day,
        d=due_day,
    )


async def _charge(s: AsyncSession, user: int, card: int, on: date, amount: str) -> None:
    await s.execute(
        text(
            "INSERT INTO expense_entries (user_id, date, amount, currency, payment_method, credit_card_id) "
            "VALUES (:u, :d, :a, 'USD', 'credit_card', :card)"
        ),
        {"u": user, "d": on, "a": amount, "card": card},
    )


class TestTheEvolutionSubtractsTheCard:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("currency", [None, "USD"])
    async def test_a_card_balance_lowers_net_worth_in_every_month_it_is_owed(self, factory, currency):
        # 1,000 USD in an account from January; a 300 USD card charge in February, never paid.
        async with factory() as s:
            await s.execute(
                text(
                    "INSERT INTO exchange_rates (date, pair, rate, source) VALUES ('2026-01-01', 'USD_ARS_MEP', 1000, :s) "
                    "ON CONFLICT (date, pair) DO NOTHING"
                ),
                {"s": _RATE_SOURCE},
            )
            user = await _user(s, "worth")
            await s.execute(
                text(
                    "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date) "
                    "VALUES (:u, :u, :n, 'bank', 'USD', 1000, '2026-01-01')"
                ),
                {"u": user.id, "n": f"{_PREFIX}acct"},
            )
            card = await _card(s, user.id, closing_day=5, due_day=15)
            await _charge(s, user.id, card, date(2026, 2, 3), "300.00")
            await s.commit()

        exchange_rate_service.invalidate_rates_cache()
        async with factory() as s:
            response = await dashboard_service.get_evolution(s, user.id, currency=currency, date_from=date(2026, 1, 1), date_to=date(2026, 2, 28))

        assert [(p.date, p.cash_balance, p.card_balance, p.private_net_worth, p.net_worth) for p in response.points] == [
            (date(2026, 1, 1), Decimal("1000"), Decimal("0"), Decimal("1000"), Decimal("1000")),
            (date(2026, 2, 1), Decimal("1000"), Decimal("300"), Decimal("700"), Decimal("700")),
        ]


class TestThePaymentsCalendarBillsTheStatementTheDueDatePays:
    @pytest.mark.asyncio
    async def test_a_card_closing_the_day_it_is_due_bills_that_days_balance(self, factory):
        # Closes and falls due on the 15th. 1,000 charged before February's statement and 500 more before
        # March's: the bill due on March 15 is March 15's statement, 1,500 — not February's 1,000.
        async with factory() as s:
            user = await _user(s, "calendar")
            card = await _card(s, user.id, closing_day=15, due_day=15)
            await _charge(s, user.id, card, date(2026, 2, 10), "1000.00")
            await _charge(s, user.id, card, date(2026, 3, 10), "500.00")
            await s.commit()

        async with factory() as s:
            response = await payments_calendar_service.get_calendar(s, user, year=2026, month=3)

        bills = [(item.date, item.amount, item.currency) for item in response.items if item.type == "card_due"]
        assert bills == [(date(2026, 3, 15), Decimal("1500.00"), "USD")]
