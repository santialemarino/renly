import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The pot-holdings read, whose correctness lives entirely in its SQL and so cannot be reached by a
# mocked session at all — a stub returns whichever rows it was handed.
#
# Two properties, and each is a decision rather than an accident:
#
#   * It is NOT filtered by is_active, unlike the two NAV queries beside it. An archived holding still
#     points at the pot, so it still blocks deleting the pot (count_holdings counts it) and it still
#     has to be movable back out. Adding an is_active clause would show an empty pot that refuses to
#     be deleted, with nothing on screen explaining why.
#   * It is filtered by pot_id, so one pot never reads another's holdings — nor a private holding,
#     which is the fail-closed direction the whole scope model rests on.
#
# Owner role, no RLS involved: this is about what the query selects, not about who may see it.
from app.repositories import pot_repository

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "pot_holdings@test.local"


# Seeds one user with two pots and, in the first, one active plus one archived holding of each kind —
# plus a private investment and a private account that must never appear, and a second pot whose
# holding must not leak into the first's. Teardown drops holdings before pots: every pot_id FK is
# RESTRICT, so the reverse order fails.
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('holdings', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        group = (
            await s.execute(text("INSERT INTO groups (name, kind, created_by) VALUES ('hold_group', 'household', :u) RETURNING id"), {"u": user})
        ).scalar_one()
        pot = (
            await s.execute(text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"), {"g": group})
        ).scalar_one()
        other_pot = (
            await s.execute(
                text("INSERT INTO pots (group_id, name, base_currency, is_default) VALUES (:g, 'hold_other', 'USD', FALSE) RETURNING id"),
                {"g": group},
            )
        ).scalar_one()

        async def investment(name: str, *, pot_id: int | None, user_id: int | None, is_active: bool) -> int:
            return (
                await s.execute(
                    text(
                        "INSERT INTO investments (user_id, pot_id, created_by, name, category, base_currency, is_active) "
                        "VALUES (:u, :p, :c, :n, 'stocks', 'USD', :a) RETURNING id"
                    ),
                    {"u": user_id, "p": pot_id, "c": user, "n": name, "a": is_active},
                )
            ).scalar_one()

        async def account(name: str, *, pot_id: int | None, user_id: int | None, is_active: bool, opening: str = "0") -> int:
            return (
                await s.execute(
                    text(
                        "INSERT INTO accounts (user_id, pot_id, created_by, name, type, currency, opening_balance, opening_date, is_active) "
                        "VALUES (:u, :p, :c, :n, 'bank', 'USD', :o, '2026-01-01', :a) RETURNING id"
                    ),
                    {"u": user_id, "p": pot_id, "c": user, "n": name, "a": is_active, "o": opening},
                )
            ).scalar_one()

        # THREE holdings of each kind, inserted middle-first, so alphabetical order differs from
        # insertion order AND from its reverse. With only two, reverse-insertion order happens to equal
        # alphabetical order and the ordering assertion passes with the order_by deleted — which is
        # exactly what a mutation run caught.
        ids = {
            "pot": pot,
            "other_pot": other_pot,
            "shared_active_investment": await investment("hold_mike", pot_id=pot, user_id=None, is_active=True),
            "shared_archived_investment": await investment("hold_alfa", pot_id=pot, user_id=None, is_active=False),
            "shared_last_investment": await investment("hold_zulu", pot_id=pot, user_id=None, is_active=True),
            "shared_active_account": await account("hold_mango", pot_id=pot, user_id=None, is_active=True),
            "shared_archived_account": await account("hold_ancla", pot_id=pot, user_id=None, is_active=False, opening="25.00"),
            "shared_last_account": await account("hold_zebra", pot_id=pot, user_id=None, is_active=True),
            "other_pots_investment": await investment("hold_other_pot", pot_id=other_pot, user_id=None, is_active=True),
            "private_investment": await investment("hold_private", pot_id=None, user_id=user, is_active=True),
            "private_account": await account("hold_private_account", pot_id=None, user_id=user, is_active=True),
            "maker": maker,
        }
        await s.commit()
    yield ids
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM investments WHERE name LIKE 'hold_%'"))
    await s.execute(text("DELETE FROM accounts WHERE name LIKE 'hold_%'"))
    await s.execute(text("DELETE FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = 'hold_group')"))
    await s.execute(text("DELETE FROM groups WHERE name = 'hold_group'"))
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


class TestArchivedHoldingsAreStillReturned:
    @pytest.mark.asyncio
    async def test_an_archived_investment_and_account_are_both_listed(self, seeded):
        # The whole point of not filtering on is_active. An is_active clause on either half makes this
        # red, and the pot page would then show nothing while pot_has_holdings kept refusing the delete.
        async with seeded["maker"]() as s:
            investments, accounts = await pot_repository.list_holdings(s, seeded["pot"])
        assert seeded["shared_archived_investment"] in [i.id for i in investments]
        assert seeded["shared_archived_account"] in [a.id for a in accounts]

    @pytest.mark.asyncio
    async def test_the_active_ones_come_back_too(self, seeded):
        # The positive control: a query returning ONLY archived rows would pass the test above.
        async with seeded["maker"]() as s:
            investments, accounts = await pot_repository.list_holdings(s, seeded["pot"])
        assert seeded["shared_active_investment"] in [i.id for i in investments]
        assert seeded["shared_active_account"] in [a.id for a in accounts]

    @pytest.mark.asyncio
    async def test_the_two_nav_queries_beside_it_DO_filter_them_out(self, seeded):
        # The counterweight, and the reason the difference is a decision rather than an oversight: an
        # archived holding is listed on the page and contributes nothing to the pot's value. If this
        # ever goes red the NAV has started counting archived money.
        async with seeded["maker"]() as s:
            investments = await pot_repository.list_active_investments(s, seeded["pot"])
            accounts = await pot_repository.list_accounts(s, seeded["pot"])
        # Sorted on both sides: neither NAV query declares an order, so comparing sequences would be
        # asserting an accident of the planner.
        assert sorted(i.id for i in investments) == sorted([seeded["shared_active_investment"], seeded["shared_last_investment"]])
        assert sorted(a.id for a in accounts) == sorted([seeded["shared_active_account"], seeded["shared_last_account"]])


class TestOnlyThisPotsHoldings:
    @pytest.mark.asyncio
    async def test_another_pots_holding_does_not_leak_in(self, seeded):
        async with seeded["maker"]() as s:
            investments, _ = await pot_repository.list_holdings(s, seeded["pot"])
        assert seeded["other_pots_investment"] not in [i.id for i in investments]

    @pytest.mark.asyncio
    async def test_a_private_holding_does_not_leak_in(self, seeded):
        # The fail-closed direction the whole scope model rests on: dropping the pot_id predicate would
        # publish one person's private holdings to every member of the group.
        async with seeded["maker"]() as s:
            investments, accounts = await pot_repository.list_holdings(s, seeded["pot"])
        assert seeded["private_investment"] not in [i.id for i in investments]
        assert seeded["private_account"] not in [a.id for a in accounts]

    @pytest.mark.asyncio
    async def test_a_pot_holding_nothing_returns_two_empty_lists_rather_than_failing(self, seeded):
        async with seeded["maker"]() as s:
            investments, accounts = await pot_repository.list_holdings(s, -1)
        assert (investments, accounts) == ([], [])


class TestOrdering:
    @pytest.mark.asyncio
    async def test_both_lists_come_back_by_name(self, seeded):
        # A stable order, so the pot page does not reshuffle between loads. The fixture names rows so
        # that alphabetical order is not insertion order, or a deleted order_by would still pass.
        async with seeded["maker"]() as s:
            investments, accounts = await pot_repository.list_holdings(s, seeded["pot"])
        assert [i.name for i in investments] == ["hold_alfa", "hold_mike", "hold_zulu"]
        assert [a.name for a in accounts] == ["hold_ancla", "hold_mango", "hold_zebra"]


class TestBalancesReachArchivedAccounts:
    @pytest.mark.asyncio
    async def test_an_archived_accounts_balance_is_still_computed(self, seeded):
        # The holdings read hands compute_account_balances_at whatever the pot holds, archived rows
        # included, so this asserts that pairing works rather than silently dropping them.
        from app.services import account_service

        async with seeded["maker"]() as s:
            _, accounts = await pot_repository.list_holdings(s, seeded["pot"])
            balances = await account_service.compute_account_balances_at(s, accounts, as_of_date=date(2026, 6, 1))
        assert balances[seeded["shared_archived_account"]] == Decimal("25.00")
