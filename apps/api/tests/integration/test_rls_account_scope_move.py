import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db import set_session_user
from app.models.user import User
from app.services import pot_service

# Moving a cash/bank ACCOUNT between a user's private scope and a pot, as the request role, against a
# real Postgres.
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
# ▸ WHAT THE GRANT DOES NOT WIDEN. Adding user_id / pot_id to the grant makes the row POLICY the only
# thing bounding where a reconciliation may be re-pointed. Its USING picks the rows the caller may
# touch, and with no WITH CHECK Postgres holds the new row to the same predicate — so the last class
# pins both ends: a row the caller cannot see is not re-pointed at all, and a row they can see cannot
# be re-pointed into a pot they cannot see. Each end is driven in two statement shapes, because a
# statement that reads a column is ALSO held to the read policy, which would mask a broken update
# policy on its own. The amounts stay outside the grant.
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
    # Not in the group at all, and holds a private account of their own.
    "outsider": "scope_move_outsider@test.local",
}
_GROUP = "scope_move_group"
# Two reconciliations on one account, so "the children follow" is about a set rather than one row.
_RECONCILED_DATES = (date(2026, 3, 1), date(2026, 4, 1))


# Seeds a group whose owner may write one pot (`pot`) and is denied view of a second (`hidden`), three
# private accounts — two of the owner's, one reconciled twice and one never, and one of the outsider's,
# reconciled once — and nothing that links any of them, so the move's own refusals stay out of the way.
# Every reconciliation carries a zero difference, which is what a movable account can hold: one with a
# difference has an adjustment row, and an account with a linked entry is refused the move outright.
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
        for key, is_default, can_view in (("pot", True, True), ("hidden", False, False)):
            pots[key] = (
                await s.execute(
                    text("INSERT INTO pots (group_id, name, base_currency, is_default) VALUES (:g, :n, 'ARS', :d) RETURNING id"),
                    {"g": group, "n": key, "d": is_default},
                )
            ).scalar_one()
            # Explicit on both rows rather than left to the visibility default: the hidden pot's whole
            # point is that this caller is refused it.
            await s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, :v, :v)"),
                {"p": pots[key], "m": seat, "v": can_view},
            )
        accounts = {}
        for key, holder in (("reconciled", "owner"), ("bare", "owner"), ("foreign", "outsider")):
            accounts[key] = (
                await s.execute(
                    text(
                        "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date)"
                        " VALUES (:u, :u, :n, 'bank', 'ARS', 100, '2026-01-01') RETURNING id"
                    ),
                    {"u": users[holder], "n": f"scope_move_{key}"},
                )
            ).scalar_one()
        for key, holder, dates in (("reconciled", "owner", _RECONCILED_DATES), ("foreign", "outsider", _RECONCILED_DATES[:1])):
            for as_of in dates:
                await s.execute(
                    text(
                        "INSERT INTO account_reconciliations"
                        " (user_id, account_id, as_of_date, statement_balance, computed_balance, difference, created_by)"
                        " VALUES (:u, :a, :d, 100, 100, 0, :u)"
                    ),
                    {"u": users[holder], "a": accounts[key], "d": as_of},
                )
        await s.commit()

    yield {
        "users": users,
        "pot": pots["pot"],
        "hidden": pots["hidden"],
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
    groups = f"SELECT id FROM groups WHERE name = '{_GROUP}'"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    accounts = "SELECT id FROM accounts WHERE name LIKE 'scope_move_%'"
    await s.execute(text(f"DELETE FROM account_reconciliations WHERE account_id IN ({accounts}) OR pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM accounts WHERE id IN ({accounts})"))
    await s.execute(text(f"DELETE FROM shared_audit_log WHERE group_id IN ({groups})"))
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"))
    await s.execute(text(f"DELETE FROM groups WHERE name = '{_GROUP}'"))
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
        # was still refused. The reconciled case is what the re-point is FOR.
        owner, pot = seeded["users"]["owner"], seeded["pot"]
        assert await _scopes(seeded, account_key) == ((owner, None), [(owner, None)] * reconciliations)

        async with _as(seeded, "owner") as s:
            await pot_service.move_holdings(s, pot, _user(seeded, "owner"), account_ids=[seeded["accounts"][account_key]], into=True)
        assert await _scopes(seeded, account_key) == ((None, pot), [(None, pot)] * reconciliations)

        async with _as(seeded, "owner") as s:
            await pot_service.move_holdings(s, pot, _user(seeded, "owner"), account_ids=[seeded["accounts"][account_key]], into=False)
        assert await _scopes(seeded, account_key) == ((owner, None), [(owner, None)] * reconciliations)


# The same re-point into the hidden pot, in the two shapes whose new row different policies check. A
# statement that READS a column (any WHERE naming one, as move_to_scope's does) also holds its new row
# to the SELECT policy, so the read policy alone would refuse it; one that reads none is bounded by the
# UPDATE policy's own check and nothing else. Measured: with that check replaced by `true`, the first
# shape is still refused and the second is admitted — so only the second pins the update policy.
_INTO_HIDDEN = {
    "reading a column": "UPDATE account_reconciliations SET user_id = NULL, pot_id = :p WHERE account_id IS NOT NULL",
    "reading none": "UPDATE account_reconciliations SET user_id = NULL, pot_id = :p",
}


# The mirror pair for the OLD row: with a column read, the SELECT policy filters the outsider's row as
# well; with none, only the update policy's USING does. Each with the rows it should re-point.
_INTO_OWN = {
    "reading a column": ("UPDATE account_reconciliations SET user_id = :u, pot_id = NULL WHERE account_id = :a", 0),
    "reading none": ("UPDATE account_reconciliations SET user_id = :u, pot_id = NULL", len(_RECONCILED_DATES)),
}


class TestTheRowPolicyBoundsEveryRePoint:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", sorted(_INTO_HIDDEN))
    async def test_a_reconciliation_cannot_be_re_pointed_into_a_pot_its_caller_cannot_see(self, seeded, shape):
        # The NEW row is held to the policy predicate: the old scope is the caller's own, so the rows are
        # reachable, and it is the destination that is refused — loudly, as a policy violation. Neither
        # statement names an account: the caller's only visible reconciliations are the owner's own.
        async with _as(seeded, "owner") as s:
            with pytest.raises(ProgrammingError, match="row-level security"):
                await s.execute(text(_INTO_HIDDEN[shape]), {"p": seeded["hidden"]})
            await s.rollback()
        owner = seeded["users"]["owner"]
        assert (await _scopes(seeded, "reconciled"))[1] == [(owner, None)] * len(_RECONCILED_DATES)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("shape", sorted(_INTO_HIDDEN))
    async def test_the_same_statement_into_a_pot_it_can_see_is_admitted(self, seeded, shape):
        # The positive control for the refusal above: identical statement, visible destination. Without
        # it, "refused" could be the grant or anything else going wrong rather than the policy's check.
        pot = seeded["pot"]
        async with _as(seeded, "owner") as s:
            result = await s.execute(text(_INTO_HIDDEN[shape]), {"p": pot})
            await s.commit()
        assert result.rowcount == len(_RECONCILED_DATES)
        assert (await _scopes(seeded, "reconciled"))[1] == [(None, pot)] * len(_RECONCILED_DATES)

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
