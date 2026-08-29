import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The seven dated sums the pot value series is built on, against a real Postgres — because every one
# of the properties below lives in the SQL, where a mocked session cannot reach it.
#
# The unit suite proves the series AGREES with the point-in-time balance when both are fed the same
# rows. It cannot prove the rows are right, and three ways they could be wrong are invisible to it:
#
#   * the `date <= until` bound. Without it a movement after the window's last point lands in the
#     final figure, and the chart's last point disagrees with the pot header.
#   * the `date >= Account.opening_date` bound. Without it a pre-opening movement is counted twice,
#     once inside opening_balance and once again here.
#   * the SCOPE predicate on transfers. A pot-scoped transfer has no user_id at all, so a bare owner
#     match drops exactly the rows a shared account's series exists to count. This was written wrong
#     first and caught by reading, not by any check — hence the test.
#
# Plus the two ownership legs, whose per-leg CASE decides which of two differently-denominated columns
# a cross-currency movement contributes. Summing one column on both sides credits the wrong figure.
#
# Owner role, no RLS involved — this is about query semantics, not visibility.
from app.repositories import (
    card_settlement_repository,
    expense_repository,
    income_repository,
    pot_ownership_repository,
    transfer_repository,
)

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAIL = "series_sums@test.local"
_OPENED = date(2026, 2, 1)
_UNTIL = date(2026, 6, 30)


# Seeds one user with a private account and a group/pot holding two shared accounts, then movements
# either side of every bound this file is about. Teardown order matters: every pot_id FK is RESTRICT.
@pytest_asyncio.fixture
async def seeded():
    engine = create_async_engine(DB_URL)
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        await _cleanup(s)
        user = (
            await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES ('series', :e, 'h') RETURNING id"), {"e": _EMAIL})
        ).scalar_one()
        group = (
            await s.execute(text("INSERT INTO groups (name, kind, created_by) VALUES ('series_group', 'household', :u) RETURNING id"), {"u": user})
        ).scalar_one()
        pot = (
            await s.execute(text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"), {"g": group})
        ).scalar_one()
        member = (
            await s.execute(
                text("INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, 'S', 'admin') RETURNING id"),
                {"g": group, "u": user},
            )
        ).scalar_one()

        private = await _account(s, "series_private", user_id=user)
        shared_a = await _account(s, "series_shared_a", pot_id=pot)
        shared_b = await _account(s, "series_shared_b", pot_id=pot)

        # Private-account movements, one inside the window and one on each side of both bounds.
        for table, amount in (("income_entries", 100), ("expense_entries", 20)):
            category = "salary" if table == "income_entries" else "other"
            for movement_date, value in ((date(2026, 1, 15), amount), (date(2026, 4, 10), amount), (date(2026, 8, 1), amount)):
                await s.execute(
                    text(f"INSERT INTO {table} (user_id, account_id, date, amount, currency, category) VALUES (:u, :a, :d, :v, 'USD', :c)"),
                    {"u": user, "a": private, "d": movement_date, "v": value, "c": category},
                )

        card = (
            await s.execute(
                text(
                    "INSERT INTO credit_cards (user_id, name, currency, closing_day, due_day) VALUES (:u, 'series_card', 'USD', 20, 28) RETURNING id"
                ),
                {"u": user},
            )
        ).scalar_one()
        # CROSS-CURRENCY on purpose: 5 cleared the card, 7 actually left the account. With the two
        # equal, summing the card leg instead of the cash leg is indistinguishable — which is exactly
        # what a mutation sweep proved about the first version of this fixture.
        await s.execute(
            text(
                "INSERT INTO card_settlements (user_id, credit_card_id, account_id, date, amount, currency, account_amount) "
                "VALUES (:u, :c, :a, '2026-04-11', 5, 'USD', 7)"
            ),
            {"u": user, "c": card, "a": private},
        )

        # A POT-SCOPED transfer between the two shared accounts, with the two legs DIFFERENT: 30 left
        # one and 31 arrived in the other. Equal legs make "both sides read from_amount" invisible.
        await s.execute(
            text(
                "INSERT INTO transfers (pot_id, from_account_id, to_account_id, date, from_amount, to_amount) "
                "VALUES (:p, :f, :t, '2026-04-12', 30, 31)"
            ),
            {"p": pot, "f": shared_a, "t": shared_b},
        )
        # A cross-currency CONTRIBUTION: 90,000 leaves the private account, 60 arrives in the pot's.
        # The per-leg CASE is what keeps those two figures on their own sides.
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events "
                "(pot_id, type, date, member_id, amount, amount_currency, base_amount, units, unit_price, "
                "from_account_id, to_account_id, created_by) "
                "VALUES (:p, 'contribution', '2026-04-13', :m, 90000, 'ARS', 60, 60, 1, :f, :t, :u)"
            ),
            {"p": pot, "m": member, "f": private, "t": shared_a, "u": user},
        )
        # Dated BEFORE the accounts opened, so the opening_date lower bound has something to exclude.
        # opening_balance already IS the balance then, so counting this would double it.
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events "
                "(pot_id, type, date, member_id, base_amount, units, unit_price, to_account_id, created_by) "
                "VALUES (:p, 'contribution', '2026-01-05', :m, 500, 500, 1, :t, :u)"
            ),
            {"p": pot, "m": member, "t": shared_a, "u": user},
        )
        await s.commit()
    yield {
        "maker": maker,
        "user": user,
        "private": private,
        "shared_a": shared_a,
        "shared_b": shared_b,
    }
    async with maker() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


async def _account(s: AsyncSession, name: str, *, user_id: int | None = None, pot_id: int | None = None) -> int:
    return (
        await s.execute(
            text(
                "INSERT INTO accounts (user_id, pot_id, created_by, name, type, currency, opening_balance, opening_date) "
                "VALUES (:u, :p, :c, :n, 'bank', 'USD', 0, :o) RETURNING id"
            ),
            {"u": user_id, "p": pot_id, "c": user_id, "n": name, "o": _OPENED},
        )
    ).scalar_one()


async def _cleanup(s: AsyncSession) -> None:
    accounts = "SELECT id FROM accounts WHERE name LIKE 'series_%'"
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE from_account_id IN ({accounts}) OR to_account_id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM transfers WHERE from_account_id IN ({accounts}) OR to_account_id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM card_settlements WHERE account_id IN ({accounts})"))
    await s.execute(text("DELETE FROM card_settlements WHERE credit_card_id IN (SELECT id FROM credit_cards WHERE name = 'series_card')"))
    await s.execute(text("DELETE FROM credit_cards WHERE name = 'series_card'"))
    await s.execute(text(f"DELETE FROM income_entries WHERE account_id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM expense_entries WHERE account_id IN ({accounts})"))
    await s.execute(text("DELETE FROM accounts WHERE name LIKE 'series_%'"))
    await s.execute(text("DELETE FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = 'series_group')"))
    await s.execute(text("DELETE FROM group_members WHERE group_id IN (SELECT id FROM groups WHERE name = 'series_group')"))
    await s.execute(text("DELETE FROM groups WHERE name = 'series_group'"))
    await s.execute(text("DELETE FROM users WHERE email = :e"), {"e": _EMAIL})


class TestTheWindowBound:
    @pytest.mark.asyncio
    async def test_a_movement_after_the_last_point_is_not_returned(self, seeded):
        # August is past `until`. Without the bound it lands in the series' final figure, and the
        # chart's last point then disagrees with the balance the pot header shows.
        async with seeded["maker"]() as s:
            rows = await income_repository.sum_by_account_ids_dated(s, [seeded["private"]], seeded["user"], until=_UNTIL)
        assert [row[1] for row in rows] == [date(2026, 4, 10)]

    @pytest.mark.asyncio
    async def test_widening_the_window_returns_it(self, seeded):
        # The positive control: the August row exists and is reachable, so the test above is measuring
        # the bound rather than a missing fixture.
        async with seeded["maker"]() as s:
            rows = await income_repository.sum_by_account_ids_dated(s, [seeded["private"]], seeded["user"], until=date(2026, 12, 31))
        assert sorted(row[1] for row in rows) == [date(2026, 4, 10), date(2026, 8, 1)]


class TestTheOpeningDateBound:
    @pytest.mark.asyncio
    async def test_a_movement_before_the_account_opened_is_excluded(self, seeded):
        # opening_balance IS the balance at opening_date, so a January row is already inside it.
        # Counting it again here double-counts — the same bound the point-in-time sums carry.
        async with seeded["maker"]() as s:
            rows = await expense_repository.sum_by_account_ids_dated(s, [seeded["private"]], seeded["user"], until=_UNTIL)
        assert [row[1] for row in rows] == [date(2026, 4, 10)]

    @pytest.mark.asyncio
    async def test_settlements_carry_the_same_two_bounds_and_sum_the_CASH_leg(self, seeded):
        # 7, not 5. A cross-currency settlement clears the card with one figure and leaves the account
        # with another; summing the card leg would debit dollars out of a peso balance.
        async with seeded["maker"]() as s:
            rows = await card_settlement_repository.sum_by_account_ids_dated(s, [seeded["private"]], seeded["user"], until=_UNTIL)
        assert rows == [(seeded["private"], date(2026, 4, 11), Decimal("7.00"))]

    @pytest.mark.asyncio
    async def test_an_ownership_event_before_the_account_opened_is_excluded(self, seeded):
        # The January contribution is inside opening_balance already; counting it here doubles it.
        async with seeded["maker"]() as s:
            rows = await pot_ownership_repository.sum_in_by_account_ids_dated(s, [seeded["shared_a"]], until=_UNTIL)
        assert [row[1] for row in rows] == [date(2026, 4, 13)]


class TestScopeOnTransfers:
    @pytest.mark.asyncio
    async def test_a_pot_scoped_transfer_is_counted_on_both_legs(self, seeded):
        # The row has no user_id, so an owner-only match returns nothing here and a shared account's
        # series silently ignores money moving between the pot's own accounts.
        async with seeded["maker"]() as s:
            out = await transfer_repository.sum_out_by_account_ids_dated(s, [seeded["shared_a"]], None, until=_UNTIL)
            incoming = await transfer_repository.sum_in_by_account_ids_dated(s, [seeded["shared_b"]], None, until=_UNTIL)
        # Each leg in its OWN amount: 30 left, 31 arrived. One column on both sides would report the
        # source figure as what the destination received.
        assert out == [(seeded["shared_a"], date(2026, 4, 12), Decimal("30.00"))]
        assert incoming == [(seeded["shared_b"], date(2026, 4, 12), Decimal("31.00"))]


class TestTheOwnershipLegs:
    @pytest.mark.asyncio
    async def test_a_cross_currency_contribution_debits_the_SOURCE_figure(self, seeded):
        # 90,000 ARS left the private account. Summing base_amount on this leg would debit 60.
        async with seeded["maker"]() as s:
            rows = await pot_ownership_repository.sum_out_by_account_ids_dated(s, [seeded["private"]], until=_UNTIL)
        assert rows == [(seeded["private"], date(2026, 4, 13), Decimal("90000.00"))]

    @pytest.mark.asyncio
    async def test_the_same_contribution_credits_the_BASE_figure(self, seeded):
        # 60 USD arrived in the pot's account. Summing `amount` on this leg would credit 90,000 into a
        # dollar balance — the exact error storing two amounts exists to prevent.
        async with seeded["maker"]() as s:
            rows = await pot_ownership_repository.sum_in_by_account_ids_dated(s, [seeded["shared_a"]], until=_UNTIL)
        assert rows == [(seeded["shared_a"], date(2026, 4, 13), Decimal("60.00"))]


class TestGrouping:
    @pytest.mark.asyncio
    async def test_two_movements_on_one_day_come_back_as_one_summed_row(self, seeded):
        # The accumulation walks each account's rows once in date order, so a day appearing twice
        # would advance the cursor past a point and drop the second figure.
        async with seeded["maker"]() as s:
            await s.execute(
                text(
                    "INSERT INTO income_entries (user_id, account_id, date, amount, currency, category) "
                    "VALUES (:u, :a, '2026-04-10', 7, 'USD', 'salary')"
                ),
                {"u": seeded["user"], "a": seeded["private"]},
            )
            await s.commit()
            rows = await income_repository.sum_by_account_ids_dated(s, [seeded["private"]], seeded["user"], until=_UNTIL)
        assert rows == [(seeded["private"], date(2026, 4, 10), Decimal("107.00"))]

    @pytest.mark.asyncio
    async def test_an_account_nobody_asked_about_is_never_returned(self, seeded):
        # The series indexes its delta map by account id and would raise on a foreign one, so the
        # `in_(account_ids)` filter is load-bearing rather than an optimisation.
        async with seeded["maker"]() as s:
            rows = await income_repository.sum_by_account_ids_dated(s, [seeded["shared_a"]], seeded["user"], until=_UNTIL)
        assert rows == []
