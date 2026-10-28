import asyncio
import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db import set_session_user
from app.models.user import User
from app.repositories import account_repository, pot_repository
from app.services import pot_service, transfer_service

# The rule that a transfer always sits in its accounts' scope — its (user_id, pot_id) is BOTH legs' — as
# the request role and the admin role against a real Postgres, and the two concurrent writes it has to
# hold against.
#
# ▸ THE SERVICE. Editing a transfer re-derives its scope from the legs it ends up with, so re-pointing a
# private transfer at two of a pot's accounts moves it into the pot. Before, the row kept its stored
# scope, and the trigger below now refuses that row — so the edit is red if the re-derive goes missing.
#
# ▸ THE TRIGGER. app_transfer_follows_accounts() refuses every row whose scope is not both legs'. Each
# misplaced row below differs from its legs in the user alone, the pot alone, both, or in one leg only
# (each direction), so a trigger that compared one column or read one leg leaves one of them admitted;
# which columns it FIRES on is pinned by an update setting each of its four columns alone. Each asserts
# the trigger's own message, so a refusal from a policy or a constraint cannot stand in for it.
#
# ▸ THE RACES, on two connections. An absorption (account deletion) locks the pot's accounts FOR UPDATE,
# moves them and re-points their transfers; a pot transfer inserted meanwhile waits on that lock through
# its foreign keys and must then be refused, not land pot-scoped on private accounts. A move into a pot
# only UPDATEs the account, which no foreign key waits for, so the transfer service locks a private
# transfer's legs first; a private transfer created meanwhile must then be refused too. Each race ends
# by reading back that no transfer has drifted — what the mutations (no FOR UPDATE in absorption, no
# lock in the service, the trigger sorted ahead of the foreign keys) each leave behind.
#
# Gated on the same two vars as the other RLS suites.

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {"owner": "xfer_scope_owner@test.local", "outsider": "xfer_scope_outsider@test.local"}
_GROUP = "xfer_scope_group"
_ON = date(2026, 2, 1)
# The trigger's own message, so a refusal from the policies or a constraint cannot stand in for it.
_REFUSED = "must sit in its accounts' scope"
# How long a race waits for the second connection to block before going on without it.
_BLOCK_WAIT_SECONDS = 5.0

# Private accounts by holder, and pot accounts by pot. a3/a4 carry no transfer, so a move of one stays
# clear of the seeded rows.
_ACCOUNTS = {
    "a1": ("owner", None),
    "a2": ("owner", None),
    "a3": ("owner", None),
    "a4": ("owner", None),
    "o1": ("outsider", None),
    "o2": ("outsider", None),
    "p1": (None, "P"),
    "p2": (None, "P"),
    "q1": (None, "Q"),
    "q2": (None, "Q"),
}


# Seeds one group whose only seat (the owner) may write two pots, P and Q, each holding two accounts;
# two private accounts of an outsider; four of the owner's; and two valid transfers, one private
# (a1 → a2) and one in P (p1 → p2).
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    admin_sessionmaker = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)
    app_sessionmaker = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        users = {}
        for key, email in _EMAILS.items():
            users[key] = (
                await s.execute(text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"), {"n": key, "e": email})
            ).scalar_one()
        group = (
            await s.execute(
                text("INSERT INTO groups (name, kind, created_by) VALUES (:g, 'household', :u) RETURNING id"), {"g": _GROUP, "u": users["owner"]}
            )
        ).scalar_one()
        seat = (
            await s.execute(
                text(
                    "INSERT INTO group_members (group_id, user_id, display_name, role, joined_at)"
                    " VALUES (:g, :u, 'owner', 'admin', NOW()) RETURNING id"
                ),
                {"g": group, "u": users["owner"]},
            )
        ).scalar_one()
        pots = {}
        for key, is_default in (("P", True), ("Q", False)):
            pots[key] = (
                await s.execute(
                    text("INSERT INTO pots (group_id, name, base_currency, is_default) VALUES (:g, :n, 'ARS', :d) RETURNING id"),
                    {"g": group, "n": key, "d": is_default},
                )
            ).scalar_one()
            await s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
                {"p": pots[key], "m": seat},
            )
        accounts = {}
        for key, (holder, pot) in _ACCOUNTS.items():
            accounts[key] = (
                await s.execute(
                    text(
                        "INSERT INTO accounts (user_id, pot_id, created_by, name, type, currency, opening_balance, opening_date)"
                        " VALUES (:u, :p, :c, :n, 'bank', 'ARS', 100, '2026-01-01') RETURNING id"
                    ),
                    {"u": users.get(holder), "p": pots.get(pot), "c": users[holder or "owner"], "n": f"xfer_scope_{key}"},
                )
            ).scalar_one()
        transfers = {}
        for key, (user_id, pot_id, legs) in {
            "private": (users["owner"], None, ("a1", "a2")),
            "pot": (None, pots["P"], ("p1", "p2")),
        }.items():
            transfers[key] = (await _insert(s, accounts, (user_id, pot_id), legs)).scalar_one()
        await s.commit()

    yield {
        "users": users,
        "group": group,
        "pots": pots,
        "accounts": accounts,
        "transfers": transfers,
        "sessionmaker": app_sessionmaker,
        "admin_sessionmaker": admin_sessionmaker,
    }

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        await s.commit()
    await app_engine.dispose()
    await admin_engine.dispose()


# Children before parents, and the pots' holdings before the pots: every pot_id FK is ON DELETE RESTRICT.
async def _cleanup(s: AsyncSession) -> None:
    groups = "SELECT id FROM groups WHERE name = :g"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    accounts = "SELECT id FROM accounts WHERE name LIKE 'xfer_scope_%'"
    params = {"g": _GROUP}
    await s.execute(
        text(f"DELETE FROM transfers WHERE from_account_id IN ({accounts}) OR to_account_id IN ({accounts}) OR pot_id IN ({pots})"), params
    )
    await s.execute(text(f"DELETE FROM accounts WHERE id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM shared_audit_log WHERE group_id IN ({groups})"), params)
    await s.execute(text(f"DELETE FROM pot_member_permissions WHERE pot_id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"), params)
    await s.execute(text(f"DELETE FROM group_members WHERE group_id IN ({groups})"), params)
    await s.execute(text("DELETE FROM groups WHERE name = :g"), params)
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS.values())})


# Inserts one 10-peso transfer between two seeded accounts with the scope given, as whoever the session is.
async def _insert(s: AsyncSession, accounts: dict, pair: tuple[int | None, int | None], legs: tuple[str, str]):
    user_id, pot_id = pair
    return await s.execute(
        text(
            "INSERT INTO transfers (user_id, pot_id, from_account_id, to_account_id, date, from_amount, to_amount)"
            " VALUES (:u, :p, :f, :t, :d, 10, 10) RETURNING id"
        ),
        {"u": user_id, "p": pot_id, "f": accounts[legs[0]], "t": accounts[legs[1]], "d": _ON},
    )


# A request-role session carrying one seeded user's context, through the real after_begin listener.
def _as(seeded, key: str) -> AsyncSession:
    session = seeded["sessionmaker"]()
    set_session_user(session, seeded["users"][key])
    return session


# The User a service call takes, detached: the services read its id and nothing they would reload.
def _user(seeded, key: str) -> User:
    return User(id=seeded["users"][key], name=key, email=_EMAILS[key], password_hash="h", session_epoch=0)


# A transfer's (user_id, pot_id), read past RLS.
async def _scope(seeded, transfer_id: int) -> tuple[int | None, int | None]:
    async with seeded["admin_sessionmaker"]() as admin:
        return tuple((await admin.execute(text("SELECT user_id, pot_id FROM transfers WHERE id = :t"), {"t": transfer_id})).one())


# Every transfer touching a seeded account whose scope is not both legs', and how many there are at all,
# read past RLS. The invariant the races are about, read the way an auditor would.
async def _drift(seeded) -> tuple[int, int]:
    async with seeded["admin_sessionmaker"]() as admin:
        row = (
            await admin.execute(
                text(
                    "SELECT count(*) FILTER (WHERE t.user_id IS DISTINCT FROM f.user_id OR t.pot_id IS DISTINCT FROM f.pot_id"
                    " OR t.user_id IS DISTINCT FROM d.user_id OR t.pot_id IS DISTINCT FROM d.pot_id), count(*)"
                    " FROM transfers t JOIN accounts f ON f.id = t.from_account_id JOIN accounts d ON d.id = t.to_account_id"
                    " WHERE f.name LIKE 'xfer_scope_%'"
                )
            )
        ).one()
    return row[0], row[1]


# Waits until some connection is waiting on a lock, or the task has finished without waiting (which is
# what a removed lock looks like). pg_locks, not pg_stat_activity: the other connection is a different
# role, and only pg_locks shows another role's waits to everybody.
async def _until_blocked_or_done(seeded, task: asyncio.Task) -> None:
    async with seeded["admin_sessionmaker"]() as probe:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + _BLOCK_WAIT_SECONDS
        while loop.time() < deadline and not task.done():
            waiting = (await probe.execute(text("SELECT count(*) FROM pg_locks WHERE NOT granted"))).scalar_one()
            await probe.rollback()
            if waiting:
                return
            await asyncio.sleep(0.05)


# Every insert the policies would never be asked about (the admin role bypasses them; the trigger holds
# for every role), as (scope, legs). Between them the written scope differs from a leg in the user alone,
# the pot alone and both, and from the FROM leg alone and the TO leg alone.
_MISPLACED = {
    "a private row on a pot's accounts": (("user", "owner"), ("p1", "p2")),
    "a pot's row on private accounts": (("pot", "P"), ("a1", "a2")),
    "a private row on another user's accounts": (("user", "owner"), ("o1", "o2")),
    "a pot's row on another pot's accounts": (("pot", "P"), ("q1", "q2")),
    "a private row whose TO leg is a pot's": (("user", "owner"), ("a1", "p1")),
    "a private row whose FROM leg is a pot's": (("user", "owner"), ("p1", "a1")),
    "a pot's row whose TO leg is private": (("pot", "P"), ("p1", "a1")),
    "a pot's row whose FROM leg is private": (("pot", "P"), ("a1", "p1")),
}


# The (user_id, pot_id) a _MISPLACED scope names.
def _pair(seeded, scope: tuple[str, str]) -> tuple[int | None, int | None]:
    kind, key = scope
    return (seeded["users"][key], None) if kind == "user" else (None, seeded["pots"][key])


class TestEditingATransferMovesItWithItsLegs:
    @pytest.mark.asyncio
    async def test_re_pointing_a_private_transfer_at_a_pots_accounts_moves_it_into_the_pot(self, seeded):
        # The service edits only its caller's private transfers (the lookup is by owner), so this is the
        # one direction an edit can take a transfer across a scope — and the one the bug was in.
        accounts, pot = seeded["accounts"], seeded["pots"]["P"]
        transfer = seeded["transfers"]["private"]
        async with _as(seeded, "owner") as s:
            moved = await transfer_service.update_transfer(
                s, transfer, _user(seeded, "owner"), from_account_id=accounts["p1"], to_account_id=accounts["p2"]
            )
        assert (moved.from_account_id, moved.to_account_id) == (accounts["p1"], accounts["p2"])
        assert await _scope(seeded, transfer) == (None, pot)
        assert await _drift(seeded) == (0, 2)

    @pytest.mark.asyncio
    async def test_an_edit_that_keeps_the_scope_keeps_it(self, seeded):
        # The positive control: re-deriving is a no-op for the edits every transfer gets, including one
        # re-pointing a leg at another of the owner's own accounts.
        accounts, owner, transfer = seeded["accounts"], seeded["users"]["owner"], seeded["transfers"]["private"]
        async with _as(seeded, "owner") as s:
            edited = await transfer_service.update_transfer(
                s, transfer, _user(seeded, "owner"), to_account_id=accounts["a3"], from_amount=Decimal("25")
            )
        assert (edited.to_account_id, edited.from_amount) == (accounts["a3"], Decimal("25"))
        assert await _scope(seeded, transfer) == (owner, None)


class TestATransferSitsInItsAccountsScope:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", sorted(_MISPLACED))
    async def test_a_transfer_cannot_be_recorded_outside_its_accounts_scope(self, seeded, case):
        scope, legs = _MISPLACED[case]
        async with seeded["admin_sessionmaker"]() as admin:
            with pytest.raises(IntegrityError, match=_REFUSED):
                await _insert(admin, seeded["accounts"], _pair(seeded, scope), legs)
            await admin.rollback()
        assert await _drift(seeded) == (0, 2)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("legs", [("p1", "p2"), ("o1", "o2")])
    async def test_the_request_role_is_refused_what_its_policy_admits(self, seeded, legs):
        # The shape of the bug, as a request makes it: the policy checks the row against its caller (a
        # private row naming the caller) and never against the legs, so only the trigger refuses it. The
        # outsider's accounts are ones the caller cannot see, which only a lookup past RLS can refuse.
        async with _as(seeded, "owner") as s:
            with pytest.raises(IntegrityError, match=_REFUSED):
                await _insert(s, seeded["accounts"], (seeded["users"]["owner"], None), legs)
            await s.rollback()
        assert await _drift(seeded) == (0, 2)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("column", "transfer", "value"),
        [
            ("pot_id", "pot", ("pot", "Q")),
            ("user_id", "private", ("user", "outsider")),
            ("from_account_id", "private", ("account", "o1")),
            ("to_account_id", "private", ("account", "o1")),
        ],
    )
    async def test_a_write_to_any_one_of_its_four_columns_is_checked(self, seeded, column, transfer, value):
        kind, key = value
        resolved = {"pot": seeded["pots"], "user": seeded["users"], "account": seeded["accounts"]}[kind][key]
        async with seeded["admin_sessionmaker"]() as admin:
            with pytest.raises(IntegrityError, match=_REFUSED):
                await admin.execute(text(f"UPDATE transfers SET {column} = :v WHERE id = :t"), {"v": resolved, "t": seeded["transfers"][transfer]})
            await admin.rollback()
        assert await _drift(seeded) == (0, 2)

    @pytest.mark.asyncio
    async def test_a_re_point_inside_the_scope_is_admitted(self, seeded):
        # The positive control for the four above: swapping the legs and moving one to another private
        # account of the same owner writes both leg columns and stays in scope.
        accounts = seeded["accounts"]
        async with seeded["admin_sessionmaker"]() as admin:
            result = await admin.execute(
                text("UPDATE transfers SET from_account_id = :f, to_account_id = :t WHERE id = :x"),
                {"f": accounts["a2"], "t": accounts["a3"], "x": seeded["transfers"]["private"]},
            )
            await admin.commit()
        assert result.rowcount == 1
        assert await _drift(seeded) == (0, 2)


class TestATransferCannotRaceAMoveOfItsAccounts:
    @pytest.mark.asyncio
    async def test_a_pot_transfer_created_during_an_absorption_is_refused(self, seeded):
        # The absorption holds the pot's accounts FOR UPDATE until it commits; the transfer, read while
        # they were still the pot's, waits on that lock through its foreign keys and is judged after it.
        accounts, owner = seeded["accounts"], seeded["users"]["owner"]
        async with seeded["admin_sessionmaker"]() as absorbing:
            assert await pot_service.absorb_group_pots(absorbing, [seeded["group"]], owner) == 4

            async def create() -> None:
                async with _as(seeded, "owner") as s:
                    await transfer_service.create_transfer(
                        s, _user(seeded, "owner"), from_account_id=accounts["p1"], to_account_id=accounts["p2"], date=_ON, from_amount=Decimal("5")
                    )

            racing = asyncio.create_task(create())
            await _until_blocked_or_done(seeded, racing)
            await absorbing.commit()
        with pytest.raises(IntegrityError, match=_REFUSED):
            await racing
        # The absorption re-pointed the seeded pot transfer with its accounts, and nothing else landed.
        assert await _scope(seeded, seeded["transfers"]["pot"]) == (owner, None)
        assert await _drift(seeded) == (0, 2)

    @pytest.mark.asyncio
    async def test_a_private_transfer_created_during_a_move_into_a_pot_is_refused(self, seeded):
        # move_holdings' own order — the pot's lock, then the account and its children — left
        # uncommitted. Its account UPDATE takes no lock a foreign key waits for, so the transfer
        # service's lock on its private legs is what makes the transfer wait.
        accounts, pot = seeded["accounts"], seeded["pots"]["P"]
        async with seeded["admin_sessionmaker"]() as moving:
            await pot_repository.lock(moving, pot)
            assert await account_repository.move_to_scope(moving, [accounts["a3"]], pot_id=pot, user_id=None) == 1

            async def create() -> None:
                async with _as(seeded, "owner") as s:
                    await transfer_service.create_transfer(
                        s, _user(seeded, "owner"), from_account_id=accounts["a3"], to_account_id=accounts["a4"], date=_ON, from_amount=Decimal("5")
                    )

            racing = asyncio.create_task(create())
            await _until_blocked_or_done(seeded, racing)
            await moving.commit()
        with pytest.raises(IntegrityError, match=_REFUSED):
            await racing
        assert await _drift(seeded) == (0, 2)
