import os
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# U21: three reads that did more work than their answer needs, each held to the answer it gave before.
#
#   * The overview's month-over-month net-worth delta compares the LAST TWO months of the net-worth series,
#     and used to build the whole series to get them — every month back to the user's first holding, the
#     same series the evolution chart builds again in the same page load. It now builds the two months it
#     compares, and the guard holds those two months to the tail of the full series in every display
#     mode, over a fixture where each term reaches the tail differently: an investment whose last snapshot
#     is months old (forward-filled), a cash account, a card carrying a balance, and a pot share.
#   * The payments calendar's paid-marking read one settlement sum per (card, bucket). It now reads them
#     in a batch per distinct date, so the statement count does not move with the number of cards — and
#     every card's paid badge is held to a literal, across the five ways a settlement can fall relative
#     to the statement it pays.
#   * In Original mode (no display currency) the dashboard built a RateLookup for the shared side twice
#     per request, each with its own settings read. It now builds one.
#
# Admin role (renly_admin, BYPASSRLS): this is about how much a read costs and what it answers, not about
# who may see what — every read here is scoped to its user by the service itself.
from app.models.user import User
from app.services import (
    account_service,
    dashboard_service,
    exchange_rate_service,
    payments_calendar_service,
    pot_service,
    settings_service,
)
from app.utils.metrics import month_over_month

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not DB_URL,
    reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_PREFIX = "u21shape_"
_RATE_SOURCE = "u21shape_test"


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


# Everything this file writes. Pot children go first (every pot_id foreign key is RESTRICT); the user's
# own rows go with the user on its cascade; the rates it seeded are tagged by source.
async def _cleanup(s: AsyncSession) -> None:
    users = "SELECT id FROM users WHERE email LIKE :p"
    groups = f"SELECT id FROM groups WHERE created_by IN ({users})"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    params = {"p": f"{_PREFIX}%"}
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM investment_snapshots WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM investments WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM accounts WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM pot_member_permissions WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM group_members WHERE group_id IN ({groups})"), params)
    await s.execute(text(f"DELETE FROM groups WHERE id IN ({groups})"), params)
    await s.execute(text(f"DELETE FROM card_settlements WHERE user_id IN ({users})"), params)
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


async def _card(s: AsyncSession, user: int, *, currency: str = "ARS", closing_day: int = 5, due_day: int = 15) -> int:
    return await _scalar(
        s,
        "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, :n, :c, :d, :cur) RETURNING id",
        u=user,
        n=f"{_PREFIX}card",
        c=closing_day,
        d=due_day,
        cur=currency,
    )


async def _charge(s: AsyncSession, user: int, card: int, on: date, amount: str, currency: str = "ARS") -> None:
    await s.execute(
        text(
            "INSERT INTO expense_entries (user_id, date, amount, currency, payment_method, credit_card_id) "
            "VALUES (:u, :d, :a, :c, 'credit_card', :card)"
        ),
        {"u": user, "d": on, "a": amount, "c": currency, "card": card},
    )


async def _settle(s: AsyncSession, user: int, card: int, on: date, amount: str, currency: str = "ARS") -> None:
    await s.execute(
        text("INSERT INTO card_settlements (credit_card_id, user_id, date, amount, currency) VALUES (:card, :u, :d, :a, :c)"),
        {"card": card, "u": user, "d": on, "a": amount, "c": currency},
    )


# Counts the statements one awaited read sends, and returns them with its result. The rate cache is
# process-wide and would make the first measurement dearer than the rest, so it is dropped first.
async def _statements(engine, read) -> tuple[list[str], object]:
    statements: list[str] = []

    def record(_conn, _cursor, statement, *_args) -> None:
        statements.append(statement)

    exchange_rate_service.invalidate_rates_cache()
    event.listen(engine.sync_engine, "before_cursor_execute", record)
    try:
        result = await read()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record)
    return statements, result


# One user whose net worth reaches the last two months through every term, each by a different route.
async def _seed_net_worth(factory) -> User:
    async with factory() as s:
        for on in (date(2019, 1, 1), date(2024, 6, 1)):
            await s.execute(
                text(
                    "INSERT INTO exchange_rates (date, pair, rate, source) VALUES (:d, 'USD_ARS_MEP', 1000, :s) ON CONFLICT (date, pair) DO NOTHING"
                ),
                {"d": on, "s": _RATE_SOURCE},
            )
        user = await _user(s, "worth")

        # A private investment valued monthly for years, then not at all for the last several months, so
        # the months the delta compares carry its last value forward rather than holding their own.
        investment = await _scalar(
            s,
            "INSERT INTO investments (user_id, created_by, name, category, base_currency) "
            "VALUES (:u, :u, :n, CAST('stocks' AS investment_category), 'USD') RETURNING id",
            u=user.id,
            n=f"{_PREFIX}inv",
        )
        for index in range(60):
            year, month = divmod(2019 * 12 + index, 12)
            await s.execute(
                text("INSERT INTO investment_snapshots (investment_id, user_id, date, value, currency) VALUES (:i, :u, :d, :v, 'USD')"),
                {"i": investment, "u": user.id, "d": date(year, month + 1, 10), "v": 1000 + index * 10},
            )

        # A peso account and a peso card, both from the start, so cash and the card liability move.
        await s.execute(
            text(
                "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date) "
                "VALUES (:u, :u, :n, 'bank', 'ARS', 500000, :d)"
            ),
            {"u": user.id, "n": f"{_PREFIX}acct", "d": date(2019, 1, 1)},
        )
        card = await _card(s, user.id)
        await _charge(s, user.id, card, date(2020, 3, 3), "120000.00")
        await _charge(s, user.id, card, date(2024, 2, 3), "30.00", currency="USD")

        # A pot this user holds 60% of, so the shared term is a real share rather than zero.
        group = await _scalar(s, "INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id", n=f"{_PREFIX}g", u=user.id)
        mine = await _scalar(
            s,
            "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, :u, 'Me', 'admin', TRUE) RETURNING id",
            g=group,
            u=user.id,
        )
        theirs = await _scalar(
            s,
            "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, NULL, 'Ana', 'member', TRUE) RETURNING id",
            g=group,
        )
        pot = await _scalar(s, "INSERT INTO pots (group_id, name, base_currency) VALUES (:g, 'pot', 'USD') RETURNING id", g=group)
        pot_investment = await _scalar(
            s,
            "INSERT INTO investments (pot_id, created_by, name, category, base_currency) "
            "VALUES (:p, :u, :n, CAST('stocks' AS investment_category), 'USD') RETURNING id",
            p=pot,
            u=user.id,
            n=f"{_PREFIX}potinv",
        )
        await s.execute(
            text("INSERT INTO investment_snapshots (investment_id, pot_id, date, value, currency) VALUES (:i, :p, :d, 200, 'USD')"),
            {"i": pot_investment, "p": pot, "d": date(2021, 5, 1)},
        )
        for member, units in ((mine, "60"), (theirs, "40")):
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, base_amount, units, unit_price, created_by) "
                    "VALUES (:p, 'opening', :d, :m, :u, :u, 1, :c)"
                ),
                {"p": pot, "d": date(2021, 5, 1), "m": member, "u": units, "c": user.id},
            )
        await s.commit()
    return user


class TestTheOverviewDeltaReadsOnlyTheMonthsItCompares:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("currency", [None, "USD", "ARS"])
    async def test_the_two_months_are_the_tail_of_the_full_series(self, maker, currency):
        _, factory = maker
        user = await _seed_net_worth(factory)
        exchange_rate_service.invalidate_rates_cache()
        async with factory() as s:
            rs = await settings_service.get_request_settings(s, user.id) if currency else None
            lookup = await exchange_rate_service.build_rate_lookup(s, rs.dollar_preference) if rs else None
            today = settings_service.today_for_timezone(rs.timezone) if rs else None
            full, _ = await dashboard_service.compute_net_worth_evolution(s, user.id, currency=currency, lookup=lookup, today=today)
            tail, _ = await dashboard_service.compute_net_worth_evolution(s, user.id, currency=currency, lookup=lookup, today=today, last_months=2)
            overview = await dashboard_service.get_overview(s, user.id, currency=currency)

        # The fixture reaches the tail through every term, and the series is long enough that taking its
        # tail is a real saving rather than the whole of it.
        print(f"\n{currency}: full series {len(full)} months, tail {len(tail)}")
        assert len(full) > 24
        last = full[-1]
        assert last.investment_value > 0 and last.cash_balance > 0 and last.card_balance > 0 and last.shared_value > 0
        assert full[-1].date > date(2024, 1, 1)  # past the last private snapshot, so the investment is forward-filled

        assert tail == full[-2:]
        prev_nw, curr_nw = month_over_month([(p.date, p.net_worth) for p in full])
        assert overview.net_worth_change == curr_nw - prev_nw
        assert overview.net_worth_change_pct == (curr_nw - prev_nw) / prev_nw

    @pytest.mark.asyncio
    async def test_the_overview_derives_two_months_not_the_whole_history(self, maker, monkeypatch):
        # The cost half: what the delta used to pay was one derived figure per month of history in each
        # per-month term. Watched at the two per-month engines the series is built on.
        _, factory = maker
        user = await _seed_net_worth(factory)
        widths: dict[str, list[int]] = {"cash": [], "pots": []}
        balance_series = account_service.compute_account_balance_series
        share_series = pot_service.compute_share_series_many

        async def cash(session, accounts, *, dates):
            widths["cash"].append(len(dates))
            return await balance_series(session, accounts, dates=dates)

        async def pots(session, seats, *, dates, lookup):
            widths["pots"].append(len(dates))
            return await share_series(session, seats, dates=dates, lookup=lookup)

        monkeypatch.setattr(account_service, "compute_account_balance_series", cash)
        monkeypatch.setattr(pot_service, "compute_share_series_many", pots)
        async with factory() as s:
            await dashboard_service.get_overview(s, user.id, currency="USD")
        # The account engine runs for the user's own accounts and again inside the pot valuation (for the
        # pots' accounts), so it is asked twice — both times for two dates, where it used to be the whole
        # grid both times.
        print(f"\nper-month engine widths: {widths}")
        assert widths["cash"] and widths["pots"]
        assert {width for calls in widths.values() for width in calls} == {2}


class TestOriginalModeBuildsOneRateLookup:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("read", ["overview", "evolution", "composition"])
    @pytest.mark.parametrize("currency", [None, "USD"])
    async def test_one_lookup_per_request(self, maker, monkeypatch, read, currency):
        engine, factory = maker
        user = await _seed_net_worth(factory)
        builds: list[str | None] = []
        build = exchange_rate_service.build_rate_lookup

        async def counted(session, dollar_preference=None):
            builds.append(dollar_preference)
            return await build(session, dollar_preference)

        monkeypatch.setattr(exchange_rate_service, "build_rate_lookup", counted)
        reads = {
            "overview": dashboard_service.get_overview,
            "evolution": dashboard_service.get_evolution,
            "composition": dashboard_service.get_composition,
        }
        async with factory() as s:
            statements, _ = await _statements(engine, lambda: reads[read](s, user.id, currency=currency))
        settings_reads = [sql for sql in statements if "FROM user_settings" in sql]
        print(f"\n{read} currency={currency}: {len(builds)} lookups, {len(settings_reads)} settings reads, {len(statements)} statements")
        assert len(builds) == 1
        # One settings read per request, with one exception: the Original-mode overview reads no request
        # settings of its own, so its finance half reads the timezone and the pot lookup reads the dollar
        # preference — two reads of one row, down from three before the lookup was shared.
        assert len(settings_reads) == (2 if (read, currency) == ("overview", None) else 1)


# Every card shares one closing and one due day, so the cards fall into ONE closing date and ONE due date
# whatever their number — the shape a statement count fixed in the number of cards has to hold for.
_YEAR, _MONTH = 2026, 3
_CLOSING, _DUE = date(2026, 3, 5), date(2026, 3, 15)


class TestThePaymentsCalendarCostsAFixedNumberOfStatements:
    # The places a settlement can fall relative to the statement closed on the 5th and due on the
    # 15th, each with the badge it must produce. Cycled over the cards, so every count holds every case.
    _CASES = (
        ("settled in full inside the window", [(date(2026, 3, 10), "1000.00")], True),
        ("settled in part inside the window", [(date(2026, 3, 10), "400.00")], False),
        ("settled only after the due date", [(date(2026, 3, 20), "1000.00")], False),
        ("half before closing, the rest inside", [(date(2026, 3, 1), "500.00"), (date(2026, 3, 12), "500.00")], True),
        # Paid in total, but most of it BEFORE the statement closed: 400 is billed and only 300 of it is
        # paid inside the window, which a window that forgot its lower bound would read as 900.
        ("mostly before closing, short inside", [(date(2026, 3, 1), "600.00"), (date(2026, 3, 12), "300.00")], False),
    )

    @classmethod
    async def _seed(cls, factory, cards: int) -> tuple[User, dict[int, bool]]:
        expected: dict[int, bool] = {}
        async with factory() as s:
            user = await _user(s, f"cal{cards}")
            for index in range(cards):
                card = await _card(s, user.id)
                await _charge(s, user.id, card, date(2026, 2, 20), "1000.00")
                _, settlements, paid = cls._CASES[index % len(cls._CASES)]
                for on, amount in settlements:
                    await _settle(s, user.id, card, on, amount)
                expected[card] = paid
            await s.commit()
        return user, expected

    @pytest.mark.asyncio
    async def test_the_count_does_not_move_with_the_number_of_cards(self, maker):
        engine, factory = maker
        counts: dict[int, int] = {}
        for cards in (5, 10):
            user, expected = await self._seed(factory, cards)
            async with factory() as s:
                statements, response = await _statements(
                    engine, lambda s=s, user=user: payments_calendar_service.get_calendar(s, user, year=_YEAR, month=_MONTH)
                )
            counts[cards] = len(statements)
            paid = {item.source_id: item.is_paid for item in response.items if item.type == "card_due"}
            # Every card produced its bill, and every bill carries the badge its settlements earn.
            assert paid == expected
            assert {item.date for item in response.items if item.type == "card_due"} == {_DUE}
        print(f"\npayments calendar statements by card count: {counts}")
        assert counts[5] == counts[10]
