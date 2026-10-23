import functools
import importlib
import os
import random
from dataclasses import dataclass
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# U19: asyncpg refuses a statement carrying more than 32,767 bind parameters, and `column.in_(ids)` binds
# one per id — so a read whose id list grows with the whole user base stops working outright once the
# list passes the cap, for every user at once. The auto-snapshot job fed every ticker-linked investment
# in the database into three such reads and would have stopped, permanently and silently, past it.
#
# Three things, each against a real Postgres because the cap belongs to the driver and the wire
# protocol, which a mocked session does not have:
#
#   * the cliff itself, so this file is known to be able to express the failure: 32,767 ids run and
#     32,768 raise;
#   * every chunked read past it (the population is CHUNKED in tests/unit/test_in_chunking.py, which
#     fails when a read is chunked with no case here), answering exactly what the same read answers over
#     only the real ids — with the ids repeated and shuffled, and again with every id in a chunk of its
#     own, which is the strongest test that merging chunks changes neither the rows nor their order;
#   * the auto-snapshot job end to end over more holdings than the cap, which is the job that failed.
#
# Admin role (renly_admin, BYPASSRLS): the scheduler's role, and this is about statement size, not
# visibility. Everything runs inside one transaction that is rolled back, so nothing is left behind.
from app.models.user import User
from app.repositories.utils import chunked
from app.services import auto_snapshot_service

DB_URL = os.getenv("LEDGER_TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.skipif(not DB_URL, reason="set LEDGER_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these"),
    pytest.mark.asyncio,
]

# The most bind parameters one statement may carry (asyncpg: "cannot exceed 32767").
_CAP = 32_767
_EMAIL = "cliff_u19_{}@test.local"
_TICKER = "CLIFFU19A"
_JAN = date(2026, 1, 10)
_FEB = date(2026, 2, 10)
_UNTIL = date(2026, 12, 31)


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(DB_URL)
    async with engine.connect() as conn:
        outer = await conn.begin()
        s = AsyncSession(bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint")
        try:
            yield s
        finally:
            await s.close()
            await outer.rollback()
    await engine.dispose()


@dataclass
class _Seed:
    users: list[int]
    groups: list[int]
    pots: list[int]
    accounts: list[int]
    investments: list[int]
    tickers: list[str]
    notifications: list[int]
    subscriptions: list[int]
    installments: list[int]


async def _scalar(s: AsyncSession, sql: str, **params):
    return (await s.execute(text(sql), params)).scalar_one()


async def _run(s: AsyncSession, sql: str, **params) -> None:
    await s.execute(text(sql), params)


# Two of everything a chunked read is keyed by, so a chunk of one id holds one key and the merge has
# something to get wrong; rows on two dates where a read is ordered or bounded by date; and a row in
# every one of the eleven sources of an account's balance. Each user also holds preference overrides and
# push browsers (the dispatch's recipient reads), and two plans of each kind carry linked expenses on
# different dates (the auto-expense job's dedup reads).
async def _seed(s: AsyncSession) -> _Seed:
    new_user = "INSERT INTO users (name, email, password_hash) VALUES ('cliff', :e, 'h') RETURNING id"
    users = [await _scalar(s, new_user, e=_EMAIL.format(n)) for n in (1, 2)]
    me = users[0]
    for user in users:
        await _run(s, """INSERT INTO user_settings (user_id, settings) VALUES (:u, '{"language": "es"}')""", u=user)

    groups, pots, seats = [], [], []
    for n in (1, 2):
        group = await _scalar(s, "INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id", n=f"cliff {n}", u=me)
        groups.append(group)
        for display, user in (("Santi", me), ("Ana", None)):
            seat = await _scalar(
                s,
                "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, :u, :d, 'member', TRUE) RETURNING id",
                g=group,
                u=user,
                d=display,
            )
            seats.append(seat)
            new_pot = "INSERT INTO pots (group_id, name, base_currency) VALUES (:g, :n, 'USD') RETURNING id"
            pot = await _scalar(s, new_pot, g=group, n=f"cliff {n} {display}")
            pots.append(pot)
            await _run(s, "INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)", p=pot, m=seat)

    private_account = (
        "INSERT INTO accounts (user_id, name, type, currency, opening_balance, opening_date, is_active) "
        "VALUES (:u, 'cliff', 'bank', 'USD', 100, :d, TRUE) RETURNING id"
    )
    pot_account = (
        "INSERT INTO accounts (pot_id, created_by, name, type, currency, opening_balance, opening_date, is_active) "
        "VALUES (:p, :u, 'cliff', 'bank', 'USD', 50, :d, TRUE) RETURNING id"
    )
    accounts = [await _scalar(s, private_account, u=me, d=_JAN) for _ in (1, 2)]
    accounts += [await _scalar(s, pot_account, p=pot, u=me, d=_JAN) for pot in pots[:2]]
    mine, other, held = accounts[0], accounts[1], accounts[2]

    for account, amount in ((mine, 10), (other, 20)):
        for on in (_JAN, _FEB):
            await _run(
                s,
                "INSERT INTO income_entries (user_id, account_id, date, amount, currency, category) VALUES (:u, :a, :d, :m, 'USD', 'salary')",
                u=me,
                a=account,
                d=on,
                m=amount,
            )
            await _run(
                s,
                "INSERT INTO expense_entries (user_id, account_id, date, amount, currency, category) VALUES (:u, :a, :d, :m, 'USD', 'food')",
                u=me,
                a=account,
                d=on,
                m=amount / 2,
            )
    await _run(
        s,
        "INSERT INTO transfers (user_id, from_account_id, to_account_id, date, from_amount, to_amount) VALUES (:u, :f, :t, :d, 5, 5)",
        u=me,
        f=mine,
        t=other,
        d=_FEB,
    )
    new_card = "INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, 'cliff', 1, 10, 'USD') RETURNING id"
    card = await _scalar(s, new_card, u=me)
    for account, on in ((mine, _JAN), (mine, _FEB), (other, _JAN)):
        await _run(
            s,
            "INSERT INTO account_reconciliations (user_id, account_id, as_of_date, statement_balance, computed_balance, difference) "
            "VALUES (:u, :a, :d, 0, 0, 0)",
            u=me,
            a=account,
            d=on,
        )
    for account, on in ((mine, _JAN), (other, _FEB)):
        await _run(
            s,
            "INSERT INTO card_settlements (user_id, credit_card_id, account_id, date, amount, currency) VALUES (:u, :c, :a, :d, 7, 'USD')",
            u=me,
            c=card,
            a=account,
            d=on,
        )
    group = groups[0]
    for account, on in ((mine, _JAN), (other, _FEB)):
        await _run(
            s,
            "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method, paid_from_account_id) "
            "VALUES (:g, :d, 9, 'USD', 'equal', :a)",
            g=group,
            d=on,
            a=account,
        )
        await _run(
            s,
            "INSERT INTO shared_income (group_id, date, amount, currency, split_method, destination, paid_to_account_id) "
            "VALUES (:g, :d, 11, 'USD', 'equal', 'joint', :a)",
            g=group,
            d=on,
            a=account,
        )
    await _run(
        s,
        "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id, to_account_id) "
        "VALUES (:g, :f, :t, :d, 3, 'USD', :fa, :ta)",
        g=group,
        f=seats[0],
        t=seats[1],
        d=_FEB,
        fa=mine,
        ta=other,
    )
    await _run(
        s,
        "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, base_amount, units, unit_price, amount, amount_currency, "
        "from_account_id, to_account_id, created_by) VALUES (:p, 'contribution', :d, :m, 4, 4, 1, 4, 'USD', :fa, :ta, :u)",
        p=pots[0],
        d=_FEB,
        m=seats[0],
        fa=mine,
        ta=held,
        u=me,
    )

    investments = []
    for pot in (None, None, pots[0], pots[1]):
        investment = await _scalar(
            s,
            "INSERT INTO investments (user_id, pot_id, created_by, name, category, base_currency, ticker, is_active) "
            "VALUES (:u, :p, :c, 'cliff', 'stocks', 'USD', :t, TRUE) RETURNING id",
            u=None if pot else me,
            p=pot,
            c=me if pot else None,
            t=_TICKER,
        )
        investments.append(investment)
        for on, quantity in ((_JAN, 3), (_FEB, 4)):
            await _run(
                s,
                "INSERT INTO investment_snapshots (investment_id, user_id, pot_id, date, value, quantity, currency) "
                "VALUES (:i, :u, :p, :d, 100, :q, 'USD')",
                i=investment,
                u=None if pot else me,
                p=pot,
                d=on,
                q=quantity,
            )
    tickers = [_TICKER, "CLIFFU19B"]
    for ticker in tickers:
        for on, price in ((_JAN, 10), (_FEB, 11)):
            await _run(s, "INSERT INTO asset_prices (ticker, date, price, currency) VALUES (:t, :d, :p, 'USD')", t=ticker, d=on, p=price)
    notifications = [
        await _scalar(s, "INSERT INTO notifications (user_id, event, digest_pending) VALUES (:u, 'pot_movement', TRUE) RETURNING id", u=user)
        for user in (users[0], users[0], users[1])
    ]
    for user, browsers in ((users[0], 2), (users[1], 1)):
        for channel in ("email", "push"):
            await _run(
                s,
                "INSERT INTO notification_preferences (user_id, event, channel, enabled) VALUES (:u, 'snapshot_due', :c, FALSE)",
                u=user,
                c=channel,
            )
        for n in range(browsers):
            await _run(
                s,
                "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, :e, 'k', 'a')",
                u=user,
                e=f"https://push.test/cliff-u20/{user}/{n}",
            )
    new_subscription = (
        "INSERT INTO subscriptions (user_id, name, amount, currency, billing_cycle, next_billing_date, anchor_day) "
        "VALUES (:u, 'cliff', 5, 'USD', 'monthly', :d, 10) RETURNING id"
    )
    new_installment = (
        "INSERT INTO installments (user_id, name, total_amount, installment_amount, currency, installments_count, start_date) "
        "VALUES (:u, 'cliff', 30, 10, 'USD', 3, :d) RETURNING id"
    )
    subscriptions = [await _scalar(s, new_subscription, u=me, d=_JAN) for _ in (1, 2)]
    installments = [await _scalar(s, new_installment, u=me, d=_JAN) for _ in (1, 2)]
    for column, plans in (("subscription_id", subscriptions), ("installment_id", installments)):
        for plan, on in ((plans[0], _JAN), (plans[0], _FEB), (plans[1], _FEB)):
            await _run(
                s,
                f"INSERT INTO expense_entries (user_id, account_id, date, amount, currency, category, {column}) "
                "VALUES (:u, :a, :d, 5, 'USD', 'food', :p)",
                u=me,
                a=mine,
                d=on,
                p=plan,
            )
    return _Seed(users, groups, pots, accounts, investments, tickers, notifications, subscriptions, installments)


def _repo(name: str):
    return getattr(importlib.import_module(f"app.repositories.{name}"), name)


# (case id, the seed field whose ids it reads, call(session, ids, seed), whether the read promises an order).
# A case id starts with the `<module>.<function>` it covers, the name tests/unit/test_in_chunking.py's
# CHUNKED uses, which holds COVERED_FUNCTIONS equal to it; a private `_sum_leg` is reached through both
# of its public legs.
_CASES = [
    (
        "snapshot_repository.get_ids_with_snapshot_on_date",
        "investments",
        lambda s, ids, _: _repo("snapshot_repository").get_ids_with_snapshot_on_date(s, ids, _FEB),
        True,
    ),
    (
        "snapshot_repository.get_latest_by_investments",
        "investments",
        lambda s, ids, _: _repo("snapshot_repository").get_latest_by_investments(s, ids),
        True,
    ),
    (
        "snapshot_repository.get_latest_by_investments as_of",
        "investments",
        lambda s, ids, _: _repo("snapshot_repository").get_latest_by_investments(s, ids, as_of_date=_JAN),
        True,
    ),
    (
        "snapshot_repository.list_by_investments",
        "investments",
        lambda s, ids, _: _repo("snapshot_repository").list_by_investments(s, ids, until=_UNTIL),
        True,
    ),
    (
        "asset_price_repository.get_latest_by_tickers",
        "tickers",
        lambda s, ids, _: _repo("asset_price_repository").get_latest_by_tickers(s, ids),
        True,
    ),
    (
        "pot_repository.list_active_investments_by_pots",
        "pots",
        lambda s, ids, _: _repo("pot_repository").list_active_investments_by_pots(s, ids),
        True,
    ),
    ("pot_repository.list_accounts_by_pots", "pots", lambda s, ids, _: _repo("pot_repository").list_accounts_by_pots(s, ids), True),
    ("pot_repository.list_permissions_by_pots", "pots", lambda s, ids, _: _repo("pot_repository").list_permissions_by_pots(s, ids), True),
    ("group_repository.get_by_ids", "groups", lambda s, ids, _: _repo("group_repository").get_by_ids(s, ids), False),
    ("group_repository.list_members_by_groups", "groups", lambda s, ids, _: _repo("group_repository").list_members_by_groups(s, ids), True),
    ("notification_repository.list_digest_pending", "users", lambda s, ids, _: _repo("notification_repository").list_digest_pending(s, ids), True),
    ("user_repository.get_by_ids", "users", lambda s, ids, _: _repo("user_repository").get_by_ids(s, ids), True),
    (
        "notification_repository.preferences_by_user_ids",
        "users",
        lambda s, ids, _: _repo("notification_repository").preferences_by_user_ids(s, ids),
        True,
    ),
    (
        "push_subscription_repository.list_by_user_ids",
        "users",
        lambda s, ids, _: _repo("push_subscription_repository").list_by_user_ids(s, ids),
        True,
    ),
    (
        "expense_repository.linked_subscription_dates_across_users",
        "subscriptions",
        lambda s, ids, _: _repo("expense_repository").linked_subscription_dates_across_users(s, ids),
        True,
    ),
    (
        "expense_repository.linked_installment_dates_across_users",
        "installments",
        lambda s, ids, _: _repo("expense_repository").linked_installment_dates_across_users(s, ids),
        True,
    ),
    (
        "user_settings_repository.get_string_by_user_ids",
        "users",
        lambda s, ids, _: _repo("user_settings_repository").get_string_by_user_ids(s, ids, "language"),
        True,
    ),
    (
        "account_repository.get_by_ids_across_users",
        "accounts",
        lambda s, ids, _: _repo("account_repository").get_by_ids_across_users(s, ids),
        False,
    ),
    (
        "account_reconciliation_repository.get_latest_dates_across_users",
        "accounts",
        lambda s, ids, _: _repo("account_reconciliation_repository").get_latest_dates_across_users(s, ids),
        True,
    ),
]
for _name in ("income_repository", "expense_repository", "card_settlement_repository"):
    _CASES += [
        (f"{_name}.sum_by_account_ids", "accounts", lambda s, ids, seed, n=_name: _repo(n).sum_by_account_ids(s, ids, seed.users[0]), True),
        (
            f"{_name}.sum_by_account_ids as_of",
            "accounts",
            lambda s, ids, seed, n=_name: _repo(n).sum_by_account_ids(s, ids, seed.users[0], as_of_date=_JAN),
            True,
        ),
        (
            f"{_name}.sum_by_account_ids_dated",
            "accounts",
            lambda s, ids, seed, n=_name: _repo(n).sum_by_account_ids_dated(s, ids, seed.users[0], until=_UNTIL),
            False,
        ),
    ]
for _name in ("shared_expense_repository", "shared_income_repository"):
    _CASES += [
        (f"{_name}.sum_by_account_ids", "accounts", lambda s, ids, _, n=_name: _repo(n).sum_by_account_ids(s, ids), True),
        (f"{_name}.sum_by_account_ids_dated", "accounts", lambda s, ids, _, n=_name: _repo(n).sum_by_account_ids_dated(s, ids, until=_UNTIL), False),
    ]
for _leg in ("in", "out"):
    _CASES += [
        (
            f"transfer_repository._sum_leg {_leg}",
            "accounts",
            lambda s, ids, seed, g=_leg: getattr(_repo("transfer_repository"), f"sum_{g}_by_account_ids")(s, ids, seed.users[0]),
            True,
        ),
        (
            f"transfer_repository._sum_leg_dated {_leg}",
            "accounts",
            lambda s, ids, seed, g=_leg: getattr(_repo("transfer_repository"), f"sum_{g}_by_account_ids_dated")(s, ids, seed.users[0], until=_UNTIL),
            False,
        ),
    ]
    for _name in ("pot_ownership_repository", "group_settlement_repository"):
        _CASES += [
            (
                f"{_name}._sum_leg {_leg}",
                "accounts",
                lambda s, ids, _, g=_leg, n=_name: getattr(_repo(n), f"sum_{g}_by_account_ids")(s, ids),
                True,
            ),
            (
                f"{_name}._sum_leg_dated {_leg}",
                "accounts",
                lambda s, ids, _, g=_leg, n=_name: getattr(_repo(n), f"sum_{g}_by_account_ids_dated")(s, ids, until=_UNTIL),
                False,
            ),
        ]
_IDS = [case[0] for case in _CASES]
# Plus the one chunked WRITE, which TestClearingTheDigestQueue covers.
COVERED_FUNCTIONS = {case_id.split(" ")[0] for case_id in _IDS} | {"notification_repository.clear_digest_pending"}


# Ids no row has, enough of them that the list is past the cap whatever the real ids are.
def _filler(field: str) -> list:
    if field == "tickers":
        return [f"ZZU19{n}" for n in range(_CAP + 1)]
    return list(range(2_000_000_000, 2_000_000_000 + _CAP + 1))


# A list read with no promised order is compared as a multiset of rows, everything else exactly.
def _comparable(result, ordered: bool):
    return result if ordered else sorted(result, key=repr)


# Points every repository's `chunked` at a chunk size of one, so each id runs in a statement of its own.
def _one_id_per_chunk(monkeypatch) -> None:
    package = importlib.import_module("app.repositories")
    for name in dir(package):
        module = importlib.import_module(f"app.repositories.{name}") if name.endswith("_repository") else None
        if module is not None and getattr(module, "chunked", None) is chunked:
            monkeypatch.setattr(module, "chunked", functools.partial(chunked, size=1))


class TestTheCliff:
    # The cap this file exists for, measured rather than recalled: without it, every case below could be
    # passing against a driver that has no such limit.
    async def test_32767_ids_run_and_32768_raise(self):
        engine = create_async_engine(DB_URL)
        try:
            async with engine.connect() as conn:
                await conn.execute(select(User.id).where(User.id.in_(range(1, _CAP + 1))))
            async with engine.connect() as conn:
                with pytest.raises(DBAPIError):
                    await conn.execute(select(User.id).where(User.id.in_(range(1, _CAP + 2))))
        finally:
            await engine.dispose()


class TestEveryChunkedRead:
    # Past the cap, with every real id repeated and the list shuffled: the same answer as the read over
    # only the real ids, which is a single statement well under it.
    @pytest.mark.parametrize(("case", "field", "call", "ordered"), _CASES, ids=_IDS)
    async def test_answers_past_the_cap_what_it_answers_under_it(self, session, case, field, call, ordered):
        seed = await _seed(session)
        real = getattr(seed, field)
        expected = await call(session, real, seed)
        assert expected, f"{case}: the seed gives this read nothing to answer, so agreeing would prove nothing"

        past_cap = real + _filler(field) + real
        random.Random(19).shuffle(past_cap)
        assert len(set(past_cap)) > _CAP
        assert _comparable(await call(session, past_cap, seed), ordered) == _comparable(expected, ordered)

    # Every id in a statement of its own, the ids given backwards and twice: merging the chunks must give
    # back the rows the one statement gives, in its order.
    @pytest.mark.parametrize(("case", "field", "call", "ordered"), _CASES, ids=_IDS)
    async def test_one_id_per_chunk_changes_neither_rows_nor_order(self, session, monkeypatch, case, field, call, ordered):
        seed = await _seed(session)
        real = getattr(seed, field)
        expected = await call(session, real, seed)
        _one_id_per_chunk(monkeypatch)
        merged = await call(session, list(reversed(real)) + real, seed)
        assert _comparable(merged, ordered) == _comparable(expected, ordered)


class TestClearingTheDigestQueue:
    # The one chunked WRITE: the count it reports is summed across chunks, and exactly the named rows change.
    async def test_clears_exactly_the_named_rows_past_the_cap(self, session):
        seed = await _seed(session)
        notifications = _repo("notification_repository")
        cleared = await notifications.clear_digest_pending(session, seed.notifications + _filler("notifications"))
        assert cleared == len(seed.notifications)
        assert await notifications.list_digest_pending(session, seed.users) == {}


class TestTheAutoSnapshotJob:
    # The job that failed: more ticker-linked holdings than the cap, all on one ticker (the shape that
    # made the undeduplicated ticker list the first read to break). It must run, and every seeded holding
    # with a quantity and a same-currency price must be snapshotted.
    async def test_runs_over_more_holdings_than_the_cap(self, session):
        seed = await _seed(session)
        await _run(
            session,
            "INSERT INTO investments (user_id, name, category, base_currency, ticker, is_active) "
            "SELECT :u, 'cliff bulk', 'stocks', 'USD', :t, TRUE FROM generate_series(1, :n)",
            u=seed.users[0],
            t=_TICKER,
            n=_CAP + 10,
        )

        created = await auto_snapshot_service.generate_auto_snapshots(session)

        snapped = await session.execute(
            text("SELECT investment_id FROM investment_snapshots WHERE investment_id = ANY(:ids) AND date = :d AND source = 'auto'"),
            {"ids": seed.investments, "d": date.today()},
        )
        assert sorted(row[0] for row in snapped.all()) == sorted(seed.investments)
        assert created >= len(seed.investments)
