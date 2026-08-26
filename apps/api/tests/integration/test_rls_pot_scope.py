import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The §7 matrix for the DUAL-SCOPE tables, proven against a real Postgres.
#
# Everything here is about the policies themselves, not the services above them. The service layer
# has its own copy of these rules (pot_service._may_view mirrors app_can_view_pot), and the failure
# that matters is the two DISAGREEING — which no unit test can see, because a mocked session returns
# whatever it was told. Only this file exercises the predicate the database actually runs.
#
# Uses the same env vars as test_rls_isolation.py so the two run together, and skips silently when
# they are unset.
from app.db import set_session_user

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {
    # Holds 100% of the pot and may write it.
    "owner": "pot_rls_owner@test.local",
    # An ACTIVE member holding 0% — the V3 case. Must see everything.
    "zero": "pot_rls_zero@test.local",
    # A member whose permission row sets can_view = false. Must see nothing.
    "denied": "pot_rls_denied@test.local",
    # In the group, and a group ADMIN — used to prove administration grants no visibility.
    "admin": "pot_rls_admin@test.local",
    # In no group at all: every existing Renly user the moment these tables ship.
    "outsider": "pot_rls_outsider@test.local",
}

# Each scoped table with the column its child rows hang off, so one parametrized test covers all six.
_SCOPED = (
    ("investments", None),
    ("investment_snapshots", "investment_id"),
    ("transactions", "investment_id"),
    ("accounts", None),
    ("account_reconciliations", "account_id"),
    ("transfers", "from_account_id"),
)


# Seeds one group with five accounts of differing access, a pot holding one shared investment and two
# shared accounts, and a full set of child rows on each — so every scoped table has a co-owned row to
# read. Also seeds a PRIVATE holding for the outsider, so "the owner branch still works" is proven
# rather than assumed. Tears everything down afterwards.
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app_sessionmaker = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    admin_sessionmaker = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        users = {}
        for key, email in _EMAILS.items():
            users[key] = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"),
                    {"n": key, "e": email},
                )
            ).scalar_one()

        group = (
            await s.execute(
                text("INSERT INTO groups (name, kind, created_by) VALUES ('pot_rls_group', 'household', :u) RETURNING id"),
                {"u": users["owner"]},
            )
        ).scalar_one()
        seats = {}
        for key in ("owner", "zero", "denied", "admin"):
            role = "admin" if key == "admin" else "member"
            seats[key] = (
                await s.execute(
                    text("INSERT INTO group_members (group_id, user_id, display_name, role, joined_at) VALUES (:g, :u, :n, :r, NOW()) RETURNING id"),
                    {"g": group, "u": users[key], "n": key, "r": role},
                )
            ).scalar_one()

        pot = (
            await s.execute(
                text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"),
                {"g": group},
            )
        ).scalar_one()
        # The owner writes; the zero-owner and the admin have no explicit row at all and therefore
        # fall back to the pot's 'members' default; the denied member is explicitly switched off.
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
            {"p": pot, "m": seats["owner"]},
        )
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, FALSE, FALSE)"),
            {"p": pot, "m": seats["denied"]},
        )
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price) VALUES (:p, 'opening', '2026-01-01', :m, 100, 1)"
            ),
            {"p": pot, "m": seats["owner"]},
        )

        shared_inv = (
            await s.execute(
                text(
                    "INSERT INTO investments (pot_id, created_by, name, category, base_currency) "
                    "VALUES (:p, :u, 'shared', 'stocks', 'USD') RETURNING id"
                ),
                {"p": pot, "u": users["owner"]},
            )
        ).scalar_one()
        await s.execute(
            text("INSERT INTO investment_snapshots (investment_id, pot_id, date, value, currency) VALUES (:i, :p, '2026-01-01', 100, 'USD')"),
            {"i": shared_inv, "p": pot},
        )
        await s.execute(
            text("INSERT INTO transactions (investment_id, pot_id, date, amount, currency, type) VALUES (:i, :p, '2026-01-01', 50, 'USD', 'buy')"),
            {"i": shared_inv, "p": pot},
        )
        accounts = []
        for name in ("shared_a", "shared_b"):
            accounts.append(
                (
                    await s.execute(
                        text(
                            "INSERT INTO accounts (pot_id, created_by, name, type, currency, opening_date) "
                            "VALUES (:p, :u, :n, 'bank', 'USD', '2026-01-01') RETURNING id"
                        ),
                        {"p": pot, "u": users["owner"], "n": name},
                    )
                ).scalar_one()
            )
        await s.execute(
            text(
                "INSERT INTO account_reconciliations (account_id, pot_id, as_of_date, statement_balance, computed_balance, difference) "
                "VALUES (:a, :p, '2026-02-01', 10, 10, 0)"
            ),
            {"a": accounts[0], "p": pot},
        )
        await s.execute(
            text(
                "INSERT INTO transfers (pot_id, from_account_id, to_account_id, date, from_amount, to_amount) VALUES (:p, :f, :t, '2026-02-01', 5, 5)"
            ),
            {"p": pot, "f": accounts[0], "t": accounts[1]},
        )
        # A private holding for the outsider, so the owner branch of the predicate is exercised too.
        await s.execute(
            text("INSERT INTO investments (user_id, created_by, name, category, base_currency) VALUES (:u, :u, 'private', 'stocks', 'USD')"),
            {"u": users["outsider"]},
        )
        await s.commit()

    yield {"users": users, "seats": seats, "group": group, "pot": pot, "accounts": accounts, "sessionmaker": app_sessionmaker}

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        await s.commit()
    await app_engine.dispose()
    await admin_engine.dispose()


# Order matters: every pot_id FK is ON DELETE RESTRICT, so the holdings have to go before the pot,
# and the pot before its group. That ordering IS the safety property being relied on elsewhere.
async def _cleanup(s: AsyncSession) -> None:
    pots = "SELECT id FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = 'pot_rls_group')"
    await s.execute(text(f"DELETE FROM transfers WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM account_reconciliations WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM transactions WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM investment_snapshots WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM investments WHERE pot_id IN ({pots})"))
    await s.execute(
        text("DELETE FROM investments WHERE name = 'private' AND user_id IN (SELECT id FROM users WHERE email = ANY(:e))"),
        {"e": list(_EMAILS.values())},
    )
    await s.execute(text(f"DELETE FROM accounts WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"))
    await s.execute(text("DELETE FROM groups WHERE name = 'pot_rls_group'"))
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS.values())})


# Opens a restricted-role session with the per-request user context set to one seeded user.
# set_session_user only records the id; the after_begin listener registered by importing app.db is
# what applies it as a GUC on every transaction — which is exactly why these tests exercise the real
# isolation mechanism rather than a reimplementation of it.
def _as(seeded, key: str) -> AsyncSession:
    session = seeded["sessionmaker"]()
    set_session_user(session, seeded["users"][key])
    return session


async def _count(session: AsyncSession, table: str) -> int:
    return (await session.execute(text(f"SELECT COUNT(*) FROM {table} WHERE pot_id IS NOT NULL"))).scalar_one()


# ---------------------------------------------------------------------------
# The §7 matrix: four questions, asked of every dual-scope table.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("table", "_fk"), _SCOPED)
@pytest.mark.asyncio
async def test_a_non_member_reads_nothing(seeded, table, _fk):
    async with _as(seeded, "outsider") as s:
        assert await _count(s, table) == 0


@pytest.mark.parametrize(("table", "_fk"), _SCOPED)
@pytest.mark.asyncio
async def test_a_member_denied_view_reads_nothing(seeded, table, _fk):
    # In the group, with a seat, and still sees none of it — the explicit permission row wins over
    # the pot's 'members' default.
    async with _as(seeded, "denied") as s:
        assert await _count(s, table) == 0


@pytest.mark.parametrize(("table", "_fk"), _SCOPED)
@pytest.mark.asyncio
async def test_a_zero_percent_member_with_view_reads_it(seeded, table, _fk):
    # V3: membership is not ownership. This member holds no units at all and has no explicit
    # permission row either — they see the pot purely through its 'members' default.
    async with _as(seeded, "zero") as s:
        assert await _count(s, table) >= 1


@pytest.mark.parametrize(("table", "_fk"), _SCOPED)
@pytest.mark.asyncio
async def test_a_member_without_write_cannot_write(seeded, table, _fk):
    # The zero-owner can SEE every row and must not be able to change one.
    #
    # RLS refuses an UPDATE by FILTERING, not by erroring: the write policy's USING clause matches no
    # rows, so the statement succeeds having touched nothing. Asserting "it raises" would therefore be
    # wrong — and asserting only "it changed nothing" would pass even if the policy were missing and
    # the WHERE clause simply matched nothing, so the OWNER's identical statement is run as the
    # positive control. The pair is the test; either half alone is not.
    async with _as(seeded, "zero") as s:
        blocked = await s.execute(text(f"UPDATE {table} SET pot_id = pot_id WHERE pot_id IS NOT NULL"))
        assert blocked.rowcount == 0
        await s.rollback()
    async with _as(seeded, "owner") as s:
        allowed = await s.execute(text(f"UPDATE {table} SET pot_id = pot_id WHERE pot_id IS NOT NULL"))
        assert allowed.rowcount >= 1
        await s.rollback()


@pytest.mark.parametrize(("table", "_fk"), _SCOPED)
@pytest.mark.asyncio
async def test_a_member_without_write_cannot_DELETE_either(seeded, table, _fk):
    # The reason each table carries TWO policies rather than one. Postgres has no WITH CHECK for
    # DELETE, so a single FOR ALL policy whose USING named app_can_view_pot would let this succeed
    # silently — a read-only member destroying a shared holding.
    async with _as(seeded, "zero") as s:
        await s.execute(text(f"DELETE FROM {table} WHERE pot_id IS NOT NULL"))
        # No error: RLS simply matches no rows for a DELETE the policy forbids.
        assert await _count(s, table) >= 1
        await s.rollback()


# ---------------------------------------------------------------------------
# The helpers themselves, and the properties the shape is supposed to guarantee.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_group_admin_gains_no_visibility_from_being_an_admin(seeded):
    # "Administration never grants visibility" (V2), and the ONLY assertion that actually proves it is
    # the second half. The admin has no explicit permission row, so on a 'members' pot they see what
    # any plain member sees — which an `OR role = 'admin'` bolted into the helper would ALSO produce,
    # leaving that widening invisible. Flipping the pot to 'owners' is what separates the two: a
    # member without a row loses access, and an admin must lose it identically.
    async with _as(seeded, "admin") as s:
        assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is True
        assert (await s.execute(text("SELECT app_can_write_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False

    async with _as(seeded, "owner") as owner:
        await owner.execute(text("UPDATE pots SET visibility = 'owners' WHERE id = :p"), {"p": seeded["pot"]})
        await owner.commit()
    try:
        async with _as(seeded, "admin") as s:
            assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False
            assert await _count(s, "investments") == 0
            assert (await s.execute(text("SELECT COUNT(*) FROM pots WHERE id = :p"), {"p": seeded["pot"]})).scalar_one() == 0
    finally:
        async with _as(seeded, "owner") as owner:
            await owner.execute(text("UPDATE pots SET visibility = 'members' WHERE id = :p"), {"p": seeded["pot"]})
            await owner.commit()


@pytest.mark.asyncio
async def test_the_visibility_default_covers_a_member_with_no_permission_row(seeded):
    # The load-bearing COALESCE: a member who joins after the pot exists has no row at all.
    async with _as(seeded, "zero") as s:
        assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is True


@pytest.mark.asyncio
async def test_an_owners_visibility_pot_fails_closed_for_anyone_without_a_row(seeded):
    async with _as(seeded, "owner") as owner:
        # The owner has an explicit row, so they keep access; the zero-owner does not and loses it.
        await owner.execute(text("UPDATE pots SET visibility = 'owners' WHERE id = :p"), {"p": seeded["pot"]})
        await owner.commit()
    try:
        async with _as(seeded, "zero") as s:
            assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False
            assert await _count(s, "investments") == 0
        async with _as(seeded, "owner") as s:
            assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is True
    finally:
        async with _as(seeded, "owner") as owner:
            await owner.execute(text("UPDATE pots SET visibility = 'members' WHERE id = :p"), {"p": seeded["pot"]})
            await owner.commit()


@pytest.mark.asyncio
async def test_deactivating_a_seat_revokes_pot_access_immediately(seeded):
    # is_active lives inside the helper, so removal and revocation are the same statement.
    async with _as(seeded, "owner") as owner:
        await owner.execute(text("UPDATE group_members SET is_active = FALSE WHERE id = :m"), {"m": seeded["seats"]["zero"]})
        await owner.commit()
    try:
        async with _as(seeded, "zero") as s:
            assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False
            assert await _count(s, "investments") == 0
    finally:
        async with _as(seeded, "owner") as owner:
            await owner.execute(text("UPDATE group_members SET is_active = TRUE WHERE id = :m"), {"m": seeded["seats"]["zero"]})
            await owner.commit()


@pytest.mark.asyncio
async def test_a_member_cannot_grant_themselves_access_to_a_pot_they_cannot_see(seeded):
    # The WITH CHECK on pot_member_permissions. Without it any authenticated user could insert a row
    # naming any pot id and their own seat, and read straight into someone else's shared money.
    async with _as(seeded, "outsider") as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view) VALUES (:p, :m, TRUE)"),
                {"p": seeded["pot"], "m": seeded["seats"]["owner"]},
            )
        await s.rollback()
    # And the pot stays unreachable, which is the property that actually matters.
    async with _as(seeded, "outsider") as s:
        assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False


@pytest.mark.asyncio
async def test_a_denied_member_cannot_turn_their_own_permission_row_back_on(seeded):
    # An UPDATE rather than an INSERT: the denied member already HAS a row, so an insert would be
    # refused by the primary key whatever the policy said — a test that passed for that reason would
    # prove nothing about RLS at all. The write policy's USING clause is what actually blocks this.
    async with _as(seeded, "denied") as s:
        blocked = await s.execute(
            text("UPDATE pot_member_permissions SET can_view = TRUE, can_write = TRUE WHERE pot_id = :p AND member_id = :m"),
            {"p": seeded["pot"], "m": seeded["seats"]["denied"]},
        )
        assert blocked.rowcount == 0
        await s.rollback()
    async with _as(seeded, "denied") as s:
        assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False


@pytest.mark.asyncio
async def test_a_member_cannot_grant_themselves_a_row_on_a_pot_they_cannot_see(seeded):
    # THE case the WITH CHECK on pot_member_permissions exists for, and the only one that exploits it:
    # a member of the group with no permission row, on an 'owners' pot. Membership already passes, so
    # a row they wrote themselves would be the whole of app_can_view_pot's remaining test — without
    # the WITH CHECK they would read straight into a pot deliberately hidden from them.
    async with _as(seeded, "owner") as owner:
        await owner.execute(text("UPDATE pots SET visibility = 'owners' WHERE id = :p"), {"p": seeded["pot"]})
        await owner.commit()
    try:
        async with _as(seeded, "zero") as s:
            assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False
            with pytest.raises(DBAPIError):
                await s.execute(
                    text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
                    {"p": seeded["pot"], "m": seeded["seats"]["zero"]},
                )
            await s.rollback()
        async with _as(seeded, "zero") as s:
            assert (await s.execute(text("SELECT app_can_view_pot(:p)"), {"p": seeded["pot"]})).scalar_one() is False
    finally:
        async with _as(seeded, "owner") as owner:
            await owner.execute(text("UPDATE pots SET visibility = 'members' WHERE id = :p"), {"p": seeded["pot"]})
            await owner.commit()


@pytest.mark.asyncio
async def test_the_private_owner_branch_still_returns_a_users_own_rows(seeded):
    # The half of the predicate that must not have regressed: after 0019 `user_id = me` still means
    # exactly "my private holdings".
    async with _as(seeded, "outsider") as s:
        assert (await s.execute(text("SELECT COUNT(*) FROM investments WHERE user_id = :u"), {"u": seeded["users"]["outsider"]})).scalar_one() == 1


@pytest.mark.asyncio
async def test_the_ledger_is_readable_by_a_zero_percent_member(seeded):
    # V5: whoever may see a pot sees every movement and every member's percentage.
    async with _as(seeded, "zero") as s:
        assert (await s.execute(text("SELECT COUNT(*) FROM pot_ownership_events WHERE pot_id = :p"), {"p": seeded["pot"]})).scalar_one() == 1


@pytest.mark.asyncio
async def test_a_zero_percent_member_cannot_write_the_ledger(seeded):
    async with _as(seeded, "zero") as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price) "
                    "VALUES (:p, 'contribution', '2026-03-01', :m, 10, 1)"
                ),
                {"p": seeded["pot"], "m": seeded["seats"]["zero"]},
            )
        await s.rollback()


@pytest.mark.asyncio
async def test_creating_a_pot_requires_the_privileged_session(seeded):
    # The bootstrap, pinned at the layer that actually refuses it. A pot's first permission row is
    # what app_can_view_pot reads, so the request session cannot establish one — which is why
    # pot_service.create_pot takes AdminSessionDep.
    # The bare INSERT is allowed — WITH CHECK is membership-only, and the caller is a member.
    async with _as(seeded, "owner") as s:
        await s.execute(
            text("INSERT INTO pots (group_id, base_currency, visibility) VALUES (:g, 'USD', 'owners')"),
            {"g": seeded["group"]},
        )
        await s.rollback()

    # RETURNING is not, and that is the whole reason creation is privileged rather than a preference:
    # a SELECT policy also applies to the row an INSERT returns, and a brand-new 'owners' pot has no
    # permission row yet, so app_can_view_pot answers false about the row being created. The service
    # needs that id back to seed the creator's permissions, so it cannot use the request session.
    async with _as(seeded, "owner") as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text("INSERT INTO pots (group_id, base_currency, visibility) VALUES (:g, 'USD', 'owners') RETURNING id"),
                {"g": seeded["group"]},
            )
        await s.rollback()


@pytest.mark.asyncio
async def test_a_context_less_session_reads_no_pot_rows_at_all(seeded):
    # Fails closed exactly like the owner match: app_current_user_id() is NULL, so nothing matches.
    async with seeded["sessionmaker"]() as s:
        for table in ("pots", "pot_member_permissions", "pot_ownership_events"):
            assert (await s.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one() == 0
