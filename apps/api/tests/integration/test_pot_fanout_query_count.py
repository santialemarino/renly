import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# U17: the dashboard values every pot its caller can see, and that must cost a FIXED number of
# statements however many pots there are. Before the batch reads it cost 28 per pot on the overview and
# 14 per pot on the evolution chart and the composition donut — 600+ statements a page at the ~20 pots
# a household is expected to hold.
#
# Two halves, each of which the other cannot stand in for:
#
#   * the COUNT, measured as statements on the wire (a cursor listener on the engine) for three users
#     holding 1, 5 and 20 identical pots, on the three dashboard reads and the pots list. Nothing is assumed about which reads are batched: a new
#     per-pot read anywhere under these endpoints shows up as a count that moves with P.
#   * the ANSWER, because a fixed count is easy to buy by answering wrongly. Every batch read is held to
#     the per-pot read it replaces over one fixture built to reach every branch a valuation has: two
#     base currencies, holdings in a third that has no rate, a month before any rate exists, an
#     unsnapshotted investment, an archived one, an undivided pot, an empty pot, a pot transfer and a
#     contribution into a pot account, across two groups.
#
# Admin role (renly_admin, BYPASSRLS): this is about how many statements a read issues and what it
# answers, not about who may see what. Every user here sees only pots they hold a seat in, because the
# seat walk filters on it whatever RLS returns.
from app.models.user import User
from app.services import dashboard_service, exchange_rate_service, pot_service, shared_worth_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_PREFIX = "fanout_"
_RATE_SOURCE = "fanout_test"
_POT_COUNTS = (1, 5, 20)
_JAN = date(2026, 1, 15)


@pytest_asyncio.fixture
async def maker():
    engine = create_async_engine(DB_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await _cleanup(s)
        await s.commit()
    yield engine, factory
    async with factory() as s:
        await _cleanup(s)
        await s.commit()
    await engine.dispose()


# Everything this file writes, torn down in FK order: every pot_id foreign key is RESTRICT, so the
# children go first, and the rates it seeded are tagged by source so nothing else's are touched.
async def _cleanup(s: AsyncSession) -> None:
    users = "SELECT id FROM users WHERE email LIKE :p"
    groups = f"SELECT id FROM groups WHERE created_by IN ({users})"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    params = {"p": f"{_PREFIX}%"}
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM transfers WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM investment_snapshots WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM investments WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM accounts WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM pot_member_permissions WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM group_members WHERE group_id IN ({groups})"), params)
    await s.execute(text(f"DELETE FROM groups WHERE id IN ({groups})"), params)
    await s.execute(text(f"DELETE FROM user_settings WHERE user_id IN ({users})"), params)
    await s.execute(text("DELETE FROM users WHERE email LIKE :p"), params)
    await s.execute(text("DELETE FROM exchange_rates WHERE source = :s"), {"s": _RATE_SOURCE})


class _Seeder:
    def __init__(self, s: AsyncSession, user: int) -> None:
        self.s = s
        self.user = user

    async def scalar(self, sql: str, **params) -> int:
        return (await self.s.execute(text(sql), params)).scalar_one()

    async def group(self, name: str) -> tuple[int, int, int]:
        group = await self.scalar("INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id", n=name, u=self.user)
        mine = await self.scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, :u, 'Santi', 'admin', TRUE) RETURNING id",
            g=group,
            u=self.user,
        )
        # A placeholder seat, so a share is a share of something rather than the whole pot.
        theirs = await self.scalar(
            "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, NULL, 'Ana', 'member', TRUE) RETURNING id",
            g=group,
        )
        return group, mine, theirs

    async def pot(self, group: int, currency: str, name: str) -> int:
        return await self.scalar("INSERT INTO pots (group_id, name, base_currency) VALUES (:g, :n, :c) RETURNING id", g=group, n=name, c=currency)

    async def investment(self, pot: int, currency: str, *, category: str = "stocks", active: bool = True, snapshots=()) -> int:
        investment = await self.scalar(
            "INSERT INTO investments (pot_id, created_by, name, category, base_currency, is_active) "
            "VALUES (:p, :u, :n, CAST(:cat AS investment_category), :c, :a) RETURNING id",
            p=pot,
            u=self.user,
            n=f"{_PREFIX}inv",
            cat=category,
            c=currency,
            a=active,
        )
        for on, value in snapshots:
            await self.s.execute(
                text("INSERT INTO investment_snapshots (investment_id, pot_id, date, value, currency) VALUES (:i, :p, :d, :v, :c)"),
                {"i": investment, "p": pot, "d": on, "v": value, "c": currency},
            )
        return investment

    async def account(self, pot: int, currency: str, opening: str, opened: date) -> int:
        return await self.scalar(
            "INSERT INTO accounts (pot_id, created_by, name, type, currency, opening_balance, opening_date, is_active) "
            "VALUES (:p, :u, :n, 'bank', :c, :o, :d, TRUE) RETURNING id",
            p=pot,
            u=self.user,
            n=f"{_PREFIX}acct",
            c=currency,
            o=opening,
            d=opened,
        )

    async def opening(self, pot: int, member: int, units: str, on: date) -> None:
        await self.s.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, base_amount, units, unit_price, created_by) "
                "VALUES (:p, 'opening', :d, :m, :u, :u, 1, :c)"
            ),
            {"p": pot, "d": on, "m": member, "u": units, "c": self.user},
        )


async def _user(s: AsyncSession, tag: str) -> int:
    return (
        await s.execute(
            text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"),
            {"n": tag, "e": f"{_PREFIX}{tag}@test.local"},
        )
    ).scalar_one()


# Seeds a rate only where none exists: a row already there is somebody else's and is neither changed
# nor re-tagged, so the source-tagged cleanup can only ever delete what this file inserted. Nothing
# here asserts on the rate's value — the comparison holds whichever rate the lookup ends up with.
async def _rates(s: AsyncSession, *, since: date) -> None:
    await s.execute(
        text("INSERT INTO exchange_rates (date, pair, rate, source) VALUES (:d, 'USD_ARS_MEP', 1000, :s) ON CONFLICT (date, pair) DO NOTHING"),
        {"d": since, "s": _RATE_SOURCE},
    )


# Counts the statements one awaited read sends to the database. The rate cache is process-wide and
# would otherwise make the first measurement one statement dearer than the rest, so it is dropped first.
async def _count(engine, read) -> tuple[int, object]:
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    exchange_rate_service.invalidate_rates_cache()
    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        result = await read()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    return len(statements), result


class TestTheDashboardCostsAFixedNumberOfStatements:
    @staticmethod
    async def _seed(factory) -> dict[int, tuple[int, int]]:
        users: dict[int, tuple[int, int]] = {}
        async with factory() as s:
            for count in _POT_COUNTS:
                user = await _user(s, f"p{count}")
                seed = _Seeder(s, user)
                group, mine, theirs = await seed.group(f"{_PREFIX}g{count}")
                # Every pot holds both kinds of holding, so every conditional read (snapshots, the
                # balance union) runs at every P and the comparison is like for like. Worth 110 USD,
                # 100 in stock plus 10 in cash, all in dollars so no stored rate can move the figure.
                # Divided 60/40, so the caller's share is 66.
                for index in range(count):
                    pot = await seed.pot(group, "USD", f"pot {index}")
                    await seed.investment(pot, "USD", snapshots=[(_JAN, "100.00")])
                    await seed.account(pot, "USD", "10.00", _JAN)
                    await seed.opening(pot, mine, "60", _JAN)
                    await seed.opening(pot, theirs, "40", _JAN)
                users[count] = (user, group)
            await s.commit()
        return users

    @pytest.mark.asyncio
    async def test_the_count_does_not_move_with_the_number_of_pots(self, maker):
        engine, factory = maker
        users = await self._seed(factory)

        reads = {
            "overview": lambda s, user, _group: dashboard_service.get_overview(s, user, currency="USD"),
            "evolution": lambda s, user, _group: dashboard_service.get_evolution(s, user, currency="USD"),
            "composition": lambda s, user, _group: dashboard_service.get_composition(s, user, currency="USD"),
            # The pots list values every pot it shows through the same batch. Scoped to the user's own
            # group: this session bypasses RLS, so the unscoped list returns EVERY pot in the database
            # for every user, and its count could not move with P whatever the code did.
            "pots": lambda s, user, group: pot_service.list_pots(
                s, User(id=user, name="u", email="u", password_hash="h", session_epoch=0), group_id=group
            ),
        }
        counts: dict[str, dict[int, int]] = {name: {} for name in reads}
        listed: dict[int, int] = {}
        for name, read in reads.items():
            for pots, (user, group) in users.items():
                async with factory() as s:
                    counts[name][pots], result = await _count(engine, lambda s=s, user=user, group=group, read=read: read(s, user, group))
                if name == "pots":
                    listed[pots] = len(result)
        print(f"\nstatements per request by pot count: {counts}")

        # The list really did value P pots — the population behind its count.
        assert listed == {pots: pots for pots in _POT_COUNTS}
        for name, by_pots in counts.items():
            assert len(set(by_pots.values())) == 1, f"{name} grows with the pot count: {by_pots}"

    @pytest.mark.asyncio
    async def test_every_pot_was_actually_valued(self, maker):
        # The population check behind the count: a fixed count would also be what a read that skipped
        # the pots altogether costs. 66 per pot is the caller's 60% of 110, so each user's shared side
        # has to be exactly P times it.
        _, factory = maker
        users = await self._seed(factory)
        for pots, (user, _) in users.items():
            exchange_rate_service.invalidate_rates_cache()
            async with factory() as s:
                context = await shared_worth_service.load_context(s, user)
                lookup = await exchange_rate_service.get_user_rate_lookup(s, user)
                worth = await shared_worth_service.get_shared_worth(s, context, currency="USD", lookup=lookup, as_of_date=date(2026, 6, 30))
            assert len(context.pots) == pots
            assert worth.pot_value == Decimal("66.00") * pots


class TestTheBatchAnswersWhatThePerPotReadAnswers:
    # Month ends from before the seeded rate (on an empty rates table January's ARS figures cannot
    # convert) to well after the last movement, so the series crosses every state a pot passes through.
    _DATES = [date(2025, 12, 31), date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31), date(2026, 4, 30), date(2026, 6, 30)]

    @staticmethod
    async def _seed(factory) -> int:
        async with factory() as s:
            # Rates only from February: on an empty rates table every ARS figure in January is
            # unconvertible. With real rates present it converts, and the comparison still holds.
            await _rates(s, since=date(2026, 2, 1))
            user = await _user(s, "rich")
            seed = _Seeder(s, user)
            household, mine, theirs = await seed.group(f"{_PREFIX}household")
            second, mine_too, _ = await seed.group(f"{_PREFIX}second")

            # USD pot, two currencies, a transfer between its accounts, an archived holding that must
            # count for nothing, and a contribution landing in one of its accounts.
            mixed = await seed.pot(household, "USD", "mixed")
            await seed.investment(mixed, "USD", snapshots=[(_JAN, "100.00"), (date(2026, 3, 10), "130.00")])
            await seed.investment(mixed, "ARS", category="crypto", snapshots=[(date(2026, 2, 1), "50000.00")])
            await seed.investment(mixed, "USD", active=False, snapshots=[(_JAN, "999.00")])
            pesos = await seed.account(mixed, "ARS", "20000.00", date(2026, 1, 1))
            dollars = await seed.account(mixed, "USD", "5.00", date(2026, 2, 1))
            await s.execute(
                text(
                    "INSERT INTO transfers (pot_id, from_account_id, to_account_id, date, from_amount, to_amount) VALUES (:p, :f, :t, :d, 10000, 10)"
                ),
                {"p": mixed, "f": pesos, "t": dollars, "d": date(2026, 3, 1)},
            )
            await seed.opening(mixed, mine, "60", _JAN)
            await seed.opening(mixed, theirs, "40", _JAN)
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events "
                    "(pot_id, type, date, member_id, amount, amount_currency, base_amount, units, unit_price, to_account_id, created_by) "
                    "VALUES (:p, 'contribution', :d, :m, 20, 'USD', 20, 10, 2, :a, :c)"
                ),
                {"p": mixed, "d": date(2026, 4, 1), "m": theirs, "a": dollars, "c": user},
            )

            # ARS pot holding dollars only.
            pesos_pot = await seed.pot(household, "ARS", "pesos")
            await seed.account(pesos_pot, "USD", "100.00", date(2026, 1, 20))
            await seed.opening(pesos_pot, mine, "100", date(2026, 2, 1))

            # Holds value nobody has divided yet.
            undivided = await seed.pot(household, "USD", "undivided")
            await seed.investment(undivided, "USD", snapshots=[(_JAN, "200.00")])

            # Holds nothing at all.
            await seed.pot(household, "USD", "empty")

            # An investment nobody has valued, beside an account whose balance must then never be read.
            unvalued = await seed.pot(household, "USD", "unvalued")
            await seed.investment(unvalued, "USD")
            await seed.account(unvalued, "USD", "50.00", _JAN)
            await seed.opening(unvalued, mine, "50", _JAN)

            # A currency with no rate at all.
            reais = await seed.pot(household, "USD", "reais")
            await seed.investment(reais, "BRL", snapshots=[(_JAN, "300.00")])
            await seed.opening(reais, mine, "10", _JAN)

            # A second group's pot, so the batch spans groups as well as pots.
            other = await seed.pot(second, "ARS", "other group")
            await seed.investment(other, "ARS", category="fci", snapshots=[(date(2026, 2, 15), "70000.00")])
            await seed.opening(other, mine_too, "1", date(2026, 2, 15))
            await s.commit()
        return user

    @pytest.mark.asyncio
    async def test_shares_valuations_and_series_match_the_per_pot_reads(self, maker):
        _, factory = maker
        user = await self._seed(factory)
        exchange_rate_service.invalidate_rates_cache()
        async with factory() as s:
            seats = await pot_service.list_visible_seats(s, user)
            lookup = await exchange_rate_service.get_user_rate_lookup(s, user)
            assert len(seats) == 7
            pots = [seat.pot for seat in seats]

            shares = []
            for as_of in self._DATES:
                one_by_one = [await pot_service.get_member_share(s, seat, as_of_date=as_of, lookup=lookup) for seat in seats]
                assert await pot_service.get_member_shares(s, seats, as_of_date=as_of, lookup=lookup) == one_by_one
                shares.extend(one_by_one)

                valuations = {pot.id: await pot_service.get_valuation(s, pot, as_of_date=as_of, lookup=lookup) for pot in pots}
                assert await pot_service.get_valuations(s, pots, as_of_date=as_of, lookup=lookup) == valuations

            one_by_one_series = [
                await pot_service.compute_share_series(s, seat.pot, seat.member_id, dates=self._DATES, events=seat.events, lookup=lookup)
                for seat in seats
            ]
            assert await pot_service.compute_share_series_many(s, seats, dates=self._DATES, lookup=lookup) == one_by_one_series

        # The fixture reaches every state it was built for — an equality between two empty or uniform
        # answers would prove nothing.
        points = [point for series in one_by_one_series for point in series]
        print(f"\n{len(shares)} shares, {len(points)} series points compared")
        assert any(share.value is not None and share.value > 0 for share in shares)
        assert any(share.value is None and share.holds_anything for share in shares)
        assert any(not share.holds_anything for share in shares)
        assert any(share.nav is not None and len(share.weights) > 1 for share in shares)
        assert any(point.my_value is not None for point in points)
        assert any(point.nav is None for point in points)
        assert any(point.nav is not None and point.my_value is None for point in points)
