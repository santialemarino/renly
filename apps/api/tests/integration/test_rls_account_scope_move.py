import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db import set_session_user
from app.models.user import User
from app.services import pot_service

# Moving a cash/bank ACCOUNT between a user's private scope and a pot, and the rule that a
# reconciliation always sits in its account's scope, as the request role against a real Postgres.
#
# ▸ WHY IT NEEDS THE DATABASE. The move re-points the account's reconciliations in the same statement
# set as the account (they carry a denormalized copy of its scope for their own policies), and
# account_reconciliations grants renly_app UPDATE per COLUMN, so whether the move works at all is a
# fact about the grant. It was once missing the scope pair, and every move answered "permission
# denied for table account_reconciliations" — for an account with no reconciliation as much as for one
# with several, because Postgres checks a column privilege against the statement, not against the rows
# it matches. A mocked session cannot see a privilege, and nor could any suite that connected as the
# owner, which is how it stayed hidden.
#
# ▸ WHERE A RECONCILIATION MAY SIT. The row policies check a reconciliation against its CALLER, never
# against its account, so on their own they let a view-only co-owner file a pot's reconciliation under
# their own name, record one naming someone else's private account, or a private one on a pot's
# account. The trigger app_reconciliation_follows_account() refuses every row whose (user_id, pot_id)
# is not its account's. Each refusal below is a row the policies ADMIT — so it is the trigger's refusal
# or nothing, and each asserts the trigger's own message so a refusal from anywhere else does not pass
# for it — and between them they differ from the account in the user alone, the pot alone, and both,
# so a trigger that COMPARES only one of the two columns is caught. Which columns it FIRES on is a
# separate fact, pinned by an update setting each of its three columns alone — pot_id and user_id as
# the request role, account_id as the admin role, since renly_app may not update it. The trigger
# runs AFTER the row, so a row the policies refuse is refused by them first and alike whatever account
# it names — one test asserts that the refusal says nothing about an account its caller cannot see.
# The positive paths prove what the trigger leaves alone: the account move, and a view-only member
# reconciling the pot's account (§34).
#
# The owner's superuser-ness does not enter into any of it: renly_app is never the owner, so its
# grants and its policies apply to it either way. Gated on the same two vars as the other RLS suites.

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {
    # Holds the accounts, may write the pot they move into, and may NOT see the second pot.
    "owner": "scope_move_owner@test.local",
    # Not in either group, and holds a private account of their own.
    "outsider": "scope_move_outsider@test.local",
    # May only VIEW a pot of a second group — the seat §34 lets reconcile, and the one the trigger is for.
    "viewer": "scope_move_viewer@test.local",
}
_GROUPS = ("scope_move_group", "scope_move_viewer_group")
# Two reconciliations on one account, so "the children follow" is about a set rather than one row.
_RECONCILED_DATES = (date(2026, 3, 1), date(2026, 4, 1))
# A date no seeded reconciliation holds, so an admitted insert is never refused by the UNIQUE instead.
_FREE_DATE = date(2026, 5, 1)
# The trigger's own message, so a refusal from the policies or a constraint cannot stand in for it.
_REFUSED = "must sit in its account's scope"


# Seeds a group whose owner may write one pot (`pot`) and is denied view of a second (`hidden`), three
# private accounts — two of the owner's, one reconciled twice and one never, and one of the outsider's,
# reconciled once — and a second group, which the owner is not in, whose pot `joint` holds an
# account reconciled once and grants the viewer VIEW only, beside a second pot (`joint_other`) the
# viewer may also view, so a re-point can change pot_id alone and stay inside what the policies admit. Nothing links any of them, so the move's own
# refusals stay out of the way. Every reconciliation carries a zero difference, which is what a movable
# account can hold: one with a difference has an adjustment row, and an account with a linked entry is
# refused the move outright.
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
        pots = {}
        # Explicit permission rows rather than the visibility default: the hidden pot's whole point is
        # that this caller is refused it, and the joint pot's that its caller may view and not write.
        for group_name, seat_holder, pot_rows in (
            (_GROUPS[0], "owner", (("pot", True, True, True), ("hidden", False, False, False))),
            (_GROUPS[1], "viewer", (("joint", True, True, False), ("joint_other", False, True, False))),
        ):
            group = (
                await s.execute(
                    text("INSERT INTO groups (name, kind, created_by) VALUES (:g, 'household', :u) RETURNING id"),
                    {"g": group_name, "u": users[seat_holder]},
                )
            ).scalar_one()
            seat = (
                await s.execute(
                    text(
                        "INSERT INTO group_members (group_id, user_id, display_name, role, joined_at)"
                        " VALUES (:g, :u, :n, 'admin', NOW()) RETURNING id"
                    ),
                    {"g": group, "u": users[seat_holder], "n": seat_holder},
                )
            ).scalar_one()
            for key, is_default, can_view, can_write in pot_rows:
                pots[key] = (
                    await s.execute(
                        text("INSERT INTO pots (group_id, name, base_currency, is_default) VALUES (:g, :n, 'ARS', :d) RETURNING id"),
                        {"g": group, "n": key, "d": is_default},
                    )
                ).scalar_one()
                await s.execute(
                    text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, :v, :w)"),
                    {"p": pots[key], "m": seat, "v": can_view, "w": can_write},
                )
        accounts = {}
        for key, holder, pot in (("reconciled", "owner", None), ("bare", "owner", None), ("foreign", "outsider", None), ("joint", None, "joint")):
            accounts[key] = (
                await s.execute(
                    text(
                        "INSERT INTO accounts (user_id, pot_id, created_by, name, type, currency, opening_balance, opening_date)"
                        " VALUES (:u, :p, :c, :n, 'bank', 'ARS', 100, '2026-01-01') RETURNING id"
                    ),
                    {"u": users.get(holder), "p": pots.get(pot), "c": users[holder or "viewer"], "n": f"scope_move_{key}"},
                )
            ).scalar_one()
        for key, holder, pot, dates in (
            ("reconciled", "owner", None, _RECONCILED_DATES),
            ("foreign", "outsider", None, _RECONCILED_DATES[:1]),
            ("joint", None, "joint", _RECONCILED_DATES[:1]),
        ):
            for as_of in dates:
                await s.execute(
                    text(
                        "INSERT INTO account_reconciliations"
                        " (user_id, pot_id, account_id, as_of_date, statement_balance, computed_balance, difference, created_by)"
                        " VALUES (:u, :p, :a, :d, 100, 100, 0, :c)"
                    ),
                    {"u": users.get(holder), "p": pots.get(pot), "a": accounts[key], "d": as_of, "c": users[holder or "viewer"]},
                )
        await s.commit()

    yield {
        "users": users,
        "pot": pots["pot"],
        "hidden": pots["hidden"],
        "joint": pots["joint"],
        "joint_other": pots["joint_other"],
        "accounts": accounts,
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
    groups = "SELECT id FROM groups WHERE name = ANY(:g)"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    accounts = "SELECT id FROM accounts WHERE name LIKE 'scope_move_%'"
    names = {"g": list(_GROUPS)}
    await s.execute(text(f"DELETE FROM account_reconciliations WHERE account_id IN ({accounts}) OR pot_id IN ({pots})"), names)
    await s.execute(text(f"DELETE FROM accounts WHERE id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM shared_audit_log WHERE group_id IN ({groups})"), names)
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"), names)
    await s.execute(text("DELETE FROM groups WHERE name = ANY(:g)"), names)
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS.values())})


# A request-role session carrying one seeded user's context, through the real after_begin listener.
def _as(seeded, key: str) -> AsyncSession:
    session = seeded["sessionmaker"]()
    set_session_user(session, seeded["users"][key])
    return session


# The User a service call takes, detached: the services read its id and nothing they would reload.
def _user(seeded, key: str) -> User:
    return User(id=seeded["users"][key], name=key, email=_EMAILS[key], password_hash="h", session_epoch=0)


# Where an account and each of its reconciliations sit, read past RLS: (user_id, pot_id) for the
# account, and the sorted list of the same pair for its reconciliations.
async def _scopes(seeded, account_key: str) -> tuple[tuple, list[tuple]]:
    account_id = seeded["accounts"][account_key]
    async with seeded["admin_sessionmaker"]() as admin:
        account = (await admin.execute(text("SELECT user_id, pot_id FROM accounts WHERE id = :a"), {"a": account_id})).one()
        children = (
            await admin.execute(
                text("SELECT user_id, pot_id FROM account_reconciliations WHERE account_id = :a ORDER BY as_of_date"), {"a": account_id}
            )
        ).all()
    return tuple(account), [tuple(child) for child in children]


class TestMovingAnAccountBetweenScopes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("account_key", "reconciliations"), [("reconciled", len(_RECONCILED_DATES)), ("bare", 0)])
    async def test_into_a_pot_and_back_out_its_reconciliations_follow(self, seeded, account_key, reconciliations):
        # THE regression, through the service a request drives. The "bare" case is the one that proves
        # the privilege is checked per statement: nothing matches the reconciliation UPDATE, and it
        # was still refused. The reconciled case is what the re-point is FOR, and it is also the proof
        # that the scope trigger admits a move: the children are re-pointed after the account, so the
        # trigger reads the account's NEW scope — in the other order it would refuse every one of them.
        owner, pot = seeded["users"]["owner"], seeded["pot"]
        assert await _scopes(seeded, account_key) == ((owner, None), [(owner, None)] * reconciliations)

        async with _as(seeded, "owner") as s:
            await pot_service.move_holdings(s, pot, _user(seeded, "owner"), account_ids=[seeded["accounts"][account_key]], into=True)
        assert await _scopes(seeded, account_key) == ((None, pot), [(None, pot)] * reconciliations)

        async with _as(seeded, "owner") as s:
            await pot_service.move_holdings(s, pot, _user(seeded, "owner"), account_ids=[seeded["accounts"][account_key]], into=False)
        assert await _scopes(seeded, account_key) == ((owner, None), [(owner, None)] * reconciliations)


# A private reconciliation re-pointed into a pot WITHOUT its account, in the two statement shapes whose
# new row different policies check. A statement that READS a column (any WHERE naming one, as
# move_to_scope's does) also holds its new row to the SELECT policy; one that reads none is bounded by
# the UPDATE policy's own check. Into the visible pot the policies admit both shapes, so the trigger is
# the only refusal. Into the hidden pot the policies refuse, and they answer first: the trigger runs
# AFTER the row, so it never judges a row the policies turned away.
_RE_POINT = {
    "reading a column": "UPDATE account_reconciliations SET user_id = NULL, pot_id = :p WHERE account_id IS NOT NULL",
    "reading none": "UPDATE account_reconciliations SET user_id = NULL, pot_id = :p",
}
_RE_POINT_REFUSAL = {"pot": (IntegrityError, _REFUSED), "hidden": (ProgrammingError, "row-level security")}


# The mirror pair for the OLD row: with a column read, the SELECT policy filters the outsider's row as
# well; with none, only the update policy's USING does. Each with the rows it should re-point — the
# caller's own two, already in the scope they are aimed at and so admitted by the trigger.
_INTO_OWN = {
    "reading a column": ("UPDATE account_reconciliations SET user_id = :u, pot_id = NULL WHERE account_id = :a", 0),
    "reading none": ("UPDATE account_reconciliations SET user_id = :u, pot_id = NULL", len(_RECONCILED_DATES)),
}


# Every insert the policies admit and the trigger refuses, as (caller, account, the scope written).
# Between them the written scope differs from the account's in the user alone (a private row naming
# another user's private account), the pot alone (a pot's row naming another pot's account), and both
# (the other two), so dropping either half of the comparison leaves one of them admitted.
_MISPLACED_INSERTS = {
    "a private row on another user's private account": ("owner", "foreign", ("user", "owner")),
    "a pot's row on another user's private account": ("viewer", "foreign", ("pot", "joint")),
    "a private row on a pot's account": ("viewer", "joint", ("user", "viewer")),
    "a pot's row on another pot's account": ("owner", "joint", ("pot", "pot")),
}


# The (user_id, pot_id) a _MISPLACED_INSERTS scope names.
def _scope_pair(seeded, scope: tuple[str, str]) -> tuple[int | None, int | None]:
    kind, key = scope
    return (seeded["users"][key], None) if kind == "user" else (None, seeded[key])


# Inserts one zero-difference reconciliation on _FREE_DATE, as whoever the session carries.
async def _insert(s: AsyncSession, seeded, account_key: str, pair: tuple[int | None, int | None], created_by: str):
    user_id, pot_id = pair
    return await s.execute(
        text(
            "INSERT INTO account_reconciliations"
            " (user_id, pot_id, account_id, as_of_date, statement_balance, computed_balance, difference, created_by)"
            " VALUES (:u, :p, :a, :d, 100, 100, 0, :c) RETURNING id"
        ),
        {"u": user_id, "p": pot_id, "a": seeded["accounts"][account_key], "d": _FREE_DATE, "c": seeded["users"][created_by]},
    )


class TestAReconciliationSitsInItsAccountsScope:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("destination", ["pot", "hidden"])
    @pytest.mark.parametrize("shape", sorted(_RE_POINT))
    async def test_a_reconciliation_cannot_be_re_pointed_away_from_its_account(self, seeded, shape, destination):
        # The owner's own reconciliations, re-pointed into a pot while their account stays private.
        # Neither statement names an account: the caller's only visible reconciliations are their own.
        owner = seeded["users"]["owner"]
        error, message = _RE_POINT_REFUSAL[destination]
        async with _as(seeded, "owner") as s:
            with pytest.raises(error, match=message):
                await s.execute(text(_RE_POINT[shape]), {"p": seeded[destination]})
            await s.rollback()
        assert (await _scopes(seeded, "reconciled"))[1] == [(owner, None)] * len(_RECONCILED_DATES)

    @pytest.mark.asyncio
    async def test_a_re_point_setting_only_pot_id_is_refused(self, seeded):
        # The trigger must fire on pot_id by itself. The viewer moves the joint pot's reconciliation to
        # the other pot they can see — admitted by the policies, since both scopes are visible to them —
        # while the account stays in the first pot.
        joint, account = seeded["joint"], seeded["accounts"]["joint"]
        async with _as(seeded, "viewer") as s:
            with pytest.raises(IntegrityError, match=_REFUSED):
                await s.execute(
                    text("UPDATE account_reconciliations SET pot_id = :p WHERE account_id = :a"), {"p": seeded["joint_other"], "a": account}
                )
            await s.rollback()
        assert (await _scopes(seeded, "joint"))[1] == [(None, joint)]

    @pytest.mark.asyncio
    async def test_a_re_point_setting_only_user_id_is_refused(self, seeded):
        # The trigger must fire on user_id by itself. The only user_id write the policies admit is the
        # caller naming themselves, so the row has to have drifted from its account first — which only an
        # account-side write can do, and the admin session does here. Re-asserting the caller's own name
        # on it is then admitted by the policies and refused by the trigger.
        owner, outsider = seeded["users"]["owner"], seeded["users"]["outsider"]
        account = seeded["accounts"]["reconciled"]
        async with seeded["admin_sessionmaker"]() as admin:
            await admin.execute(text("UPDATE accounts SET user_id = :u WHERE id = :a"), {"u": outsider, "a": account})
            await admin.commit()
        async with _as(seeded, "owner") as s:
            with pytest.raises(IntegrityError, match=_REFUSED):
                await s.execute(text("UPDATE account_reconciliations SET user_id = :u WHERE account_id = :a"), {"u": owner, "a": account})
            await s.rollback()
        assert await _scopes(seeded, "reconciled") == ((outsider, None), [(owner, None)] * len(_RECONCILED_DATES))

    @pytest.mark.asyncio
    async def test_a_re_point_setting_only_account_id_is_refused(self, seeded):
        # The trigger must fire on account_id by itself. renly_app is not granted UPDATE on it, so only the
        # admin role can issue this write — and the trigger holds for every role. The positive control
        # first: one of the owner's reconciliations moved to the owner's other private account stays in
        # its scope and is admitted, so what is refused is the destination and not the verb. Then the
        # outsider's reconciliation moved onto the owner's account, whose scope differs in the user.
        owner, outsider = seeded["users"]["owner"], seeded["users"]["outsider"]
        accounts = seeded["accounts"]
        statement = "UPDATE account_reconciliations SET account_id = :to WHERE account_id = :a AND as_of_date = :d"
        async with seeded["admin_sessionmaker"]() as admin:
            moved = await admin.execute(text(statement), {"to": accounts["bare"], "a": accounts["reconciled"], "d": _RECONCILED_DATES[1]})
            assert moved.rowcount == 1
            with pytest.raises(IntegrityError, match=_REFUSED):
                await admin.execute(text(statement), {"to": accounts["bare"], "a": accounts["foreign"], "d": _RECONCILED_DATES[0]})
            await admin.rollback()
        assert (await _scopes(seeded, "foreign"))[1] == [(outsider, None)]
        assert (await _scopes(seeded, "bare"))[1] == []
        assert (await _scopes(seeded, "reconciled"))[1] == [(owner, None)] * len(_RECONCILED_DATES)

    @pytest.mark.asyncio
    async def test_a_refusal_says_nothing_about_an_account_its_caller_cannot_see(self, seeded):
        # Guessing the scope of an account the caller cannot see — right and wrong, as a user and as a pot
        # — must be refused the same way. Were the trigger to run ahead of the policies, a right guess
        # would pass it and reach the policy (42501) while a wrong one stopped at it (23514), and the
        # SQLSTATE alone would confirm who holds the account.
        outsider, joint = seeded["users"]["outsider"], seeded["joint"]
        probes = {
            "user, right": ("foreign", (outsider, None)),
            "user, wrong": ("joint", (outsider, None)),
            "pot, right": ("joint", (None, joint)),
            "pot, wrong": ("foreign", (None, joint)),
        }
        states = {}
        for probe, (account_key, pair) in probes.items():
            async with _as(seeded, "owner") as s:
                with pytest.raises(DBAPIError) as refused:
                    await _insert(s, seeded, account_key, pair, "owner")
                states[probe] = refused.value.orig.sqlstate
                await s.rollback()
        assert states == dict.fromkeys(probes, "42501")

    @pytest.mark.asyncio
    async def test_a_view_only_member_cannot_file_a_pots_reconciliation_under_their_own_name(self, seeded):
        # The verb 0031's grant opened: the policies admit it (the viewer may see the pot the row leaves,
        # and the row it becomes is their own), and it would hide the row from every other member while
        # its UNIQUE (account_id, as_of_date) kept refusing their reconcile on that date. The positive
        # control first: the same statement aimed at the account's own scope is admitted, so what is
        # refused is the destination and not the verb.
        joint, account, viewer = seeded["joint"], seeded["accounts"]["joint"], seeded["users"]["viewer"]
        statement = "UPDATE account_reconciliations SET user_id = :u, pot_id = :p WHERE account_id = :a"
        async with _as(seeded, "viewer") as s:
            result = await s.execute(text(statement), {"u": None, "p": joint, "a": account})
            assert result.rowcount == 1
            with pytest.raises(IntegrityError, match=_REFUSED):
                await s.execute(text(statement), {"u": viewer, "p": None, "a": account})
            await s.rollback()
        assert (await _scopes(seeded, "joint"))[1] == [(None, joint)]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("case", sorted(_MISPLACED_INSERTS))
    async def test_a_reconciliation_cannot_be_recorded_outside_its_accounts_scope(self, seeded, case):
        # The two older holes and their two siblings. The trigger reads the account past RLS, which the
        # cases naming the outsider's account depend on: its caller cannot see it, and a lookup filtered
        # by their policies would find no account and have nothing to refuse.
        caller, account_key, scope = _MISPLACED_INSERTS[case]
        async with _as(seeded, caller) as s:
            with pytest.raises(IntegrityError, match=_REFUSED):
                await _insert(s, seeded, account_key, _scope_pair(seeded, scope), caller)
            await s.rollback()
        async with seeded["admin_sessionmaker"]() as admin:
            recorded = await admin.execute(
                text("SELECT count(*) FROM account_reconciliations WHERE account_id = :a AND as_of_date = :d"),
                {"a": seeded["accounts"][account_key], "d": _FREE_DATE},
            )
            assert recorded.scalar_one() == 0

    @pytest.mark.asyncio
    async def test_a_view_only_member_still_reconciles_the_pots_account(self, seeded):
        # §34: whoever can SEE a pot may reconcile its accounts. The trigger leaves every verb that keeps
        # a row in its account's scope — recording one, patching its back-pointer, deleting it — which is
        # also the positive control for the insert refused above on this same account and date.
        joint = seeded["joint"]
        async with _as(seeded, "viewer") as s:
            recorded = (await _insert(s, seeded, "joint", (None, joint), "viewer")).scalar_one()
            patched = await s.execute(text("UPDATE account_reconciliations SET adjustment_shared_expense_id = NULL WHERE id = :r"), {"r": recorded})
            assert patched.rowcount == 1
            await s.commit()
        assert (await _scopes(seeded, "joint"))[1] == [(None, joint), (None, joint)]
        async with _as(seeded, "viewer") as s:
            deleted = await s.execute(text("DELETE FROM account_reconciliations WHERE id = :r"), {"r": recorded})
            await s.commit()
        assert deleted.rowcount == 1
        assert (await _scopes(seeded, "joint"))[1] == [(None, joint)]


class TestTheRowPolicyBoundsEveryRePoint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", sorted(_INTO_OWN))
    async def test_a_reconciliation_its_caller_cannot_see_is_not_re_pointed(self, seeded, shape):
        # The OLD row is filtered, so somebody else's reconciliation is simply not matched — the refusal
        # is "nothing changed", which is why the assertion reads the row back rather than waiting for an
        # error. Aimed at the caller's own scope, the most tempting destination. The statement reading
        # no column matches every row the update policy admits, so it also re-points the caller's own
        # two, which are already there; the outsider's is the one that must not move.
        statement, moved = _INTO_OWN[shape]
        owner = seeded["users"]["owner"]
        async with _as(seeded, "owner") as s:
            result = await s.execute(text(statement), {"u": owner, "a": seeded["accounts"]["foreign"]})
            await s.commit()
        assert (await _scopes(seeded, "foreign"))[1] == [(seeded["users"]["outsider"], None)]
        assert result.rowcount == moved

    @pytest.mark.asyncio
    async def test_the_amounts_stay_outside_the_grant(self, seeded):
        # The grant widened by the scope pair and by nothing else: a figure on the caller's OWN row is
        # still refused, by the grant and so as an error rather than as a filtered no-op.
        account = seeded["accounts"]["reconciled"]
        async with _as(seeded, "owner") as s:
            with pytest.raises(ProgrammingError, match="permission denied"):
                await s.execute(text("UPDATE account_reconciliations SET statement_balance = 999 WHERE account_id = :a"), {"a": account})
            await s.rollback()
        async with seeded["admin_sessionmaker"]() as admin:
            balances = (
                await admin.execute(text("SELECT statement_balance FROM account_reconciliations WHERE account_id = :a"), {"a": account})
            ).scalars()
            assert list(balances) == [Decimal("100.00")] * len(_RECONCILED_DATES)
