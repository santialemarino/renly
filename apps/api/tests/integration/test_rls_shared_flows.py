import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The §7 matrix for the four SHARED-FLOW tables, proven against a real Postgres.
#
# These policies are the confidentiality boundary of the flow half: a shared expense names what a
# household spent and a settlement names what one person paid another, and both are readable by every
# member of the group and nobody else. The service layer has its own membership gate
# (group_service.require_member), and the failure that matters is the two disagreeing — which no unit
# test can see, because a mocked session returns whatever it was told.
#
# Two of the four carry a SECOND read branch for rows naming an account or card the caller owns. That
# branch is not a widening of the model, it is what keeps a PRIVATE balance correct when a member
# leaves: without it the row vanishes from their balance query and their own account silently gains
# back money it no longer holds. Its exact boundary — what a former member can and cannot then see —
# is what the last class here pins.
#
# Uses the same env vars as test_rls_isolation.py so the RLS suites run together.
from app.db import set_session_user

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {
    # An active member, and the one who fronted the group's expense from their own account.
    "payer": "flow_rls_payer@test.local",
    # An active member who fronted nothing.
    "member": "flow_rls_member@test.local",
    # A member who is later DEACTIVATED, to exercise the account-leg read branch.
    "leaver": "flow_rls_leaver@test.local",
    # In no group at all: every existing Renly user the moment these tables ship.
    "outsider": "flow_rls_outsider@test.local",
}

# The four tables and the column their membership is keyed through. group_money_settings is keyed by
# its own primary key, which IS the group id.
_FLOW_TABLES = ("group_money_settings", "shared_expenses", "shared_expense_splits", "group_settlements")


async def _scalar(session: AsyncSession, sql: str, **params):
    return (await session.execute(text(sql), params)).scalar_one()


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM users WHERE email = ANY(:emails)"), {"emails": list(_EMAILS.values())})
    await session.execute(text("DELETE FROM groups WHERE name = 'Flow RLS group'"))
    await session.commit()


# One group with three seats, a money-settings row, one shared expense funded from the payer's own
# account and split three ways, and one settlement between two of the seats. Everything the four
# policies have to protect, in the smallest fixture that has all of it.
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app_sessionmaker = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    admin_sessionmaker = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        users = {
            key: await _scalar(s, "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id", n=key, e=email)
            for key, email in _EMAILS.items()
        }
        group = await _scalar(
            s, "INSERT INTO groups (name, kind, created_by) VALUES ('Flow RLS group', 'household', :u) RETURNING id", u=users["payer"]
        )
        await s.execute(text("INSERT INTO group_money_settings (group_id) VALUES (:g)"), {"g": group})
        seats = {
            key: await _scalar(
                s,
                "INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, :n, :r) RETURNING id",
                g=group,
                u=users[key],
                n=key,
                r="admin" if key == "payer" else "member",
            )
            for key in ("payer", "member", "leaver")
        }
        account = await _scalar(
            s,
            "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date)"
            " VALUES (:u, :u, 'Payer account', 'bank', 'ARS', 100000, '2026-01-01') RETURNING id",
            u=users["payer"],
        )
        # The leaver's own account, so the read branch has something of THEIRS to match on.
        leaver_account = await _scalar(
            s,
            "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date)"
            " VALUES (:u, :u, 'Leaver account', 'bank', 'ARS', 5000, '2026-01-01') RETURNING id",
            u=users["leaver"],
        )
        expense = await _scalar(
            s,
            "INSERT INTO shared_expenses (group_id, date, amount, currency, category, split_method, paid_from_account_id)"
            " VALUES (:g, '2026-06-01', 9000, 'ARS', 'dining', 'equal', :a) RETURNING id",
            g=group,
            a=account,
        )
        # A second expense funded from the LEAVER's account, which is the row their branch must keep.
        leaver_expense = await _scalar(
            s,
            "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method, paid_from_account_id)"
            " VALUES (:g, '2026-06-02', 600, 'ARS', 'equal', :a) RETURNING id",
            g=group,
            a=leaver_account,
        )
        for seat in seats.values():
            await s.execute(
                text("INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount, paid_amount) VALUES (:e, :g, :m, 3000, :p)"),
                {"e": expense, "g": group, "m": seat, "p": 9000 if seat == seats["payer"] else 0},
            )
        settlement = await _scalar(
            s,
            "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, from_account_id)"
            " VALUES (:g, :f, :t, '2026-06-05', 3000, 'ARS', :a) RETURNING id",
            g=group,
            f=seats["leaver"],
            t=seats["payer"],
            a=leaver_account,
        )
        await s.commit()

    context = {
        "users": users,
        "group": group,
        "seats": seats,
        "account": account,
        "leaver_account": leaver_account,
        "expense": expense,
        "leaver_expense": leaver_expense,
        "settlement": settlement,
        "app": app_sessionmaker,
        "admin": admin_sessionmaker,
    }
    yield context

    async with admin_sessionmaker() as s:
        await _cleanup(s)
    await app_engine.dispose()
    await admin_engine.dispose()


# Runs a query on the RESTRICTED role with the given user's context set — the shape a real request has.
# set_session_user only RECORDS the id; the after_begin listener registered by importing app.db is what
# applies it as a GUC on every transaction, so these exercise the real isolation mechanism rather than a
# reimplementation of it.
async def _as_user(seeded, user_id: int, sql: str, **params):
    async with seeded["app"]() as s:
        set_session_user(s, user_id)
        return (await s.execute(text(sql), params)).all()


class TestAMemberSeesTheirGroupsMoney:
    @pytest.mark.parametrize("table", _FLOW_TABLES)
    @pytest.mark.asyncio
    async def test_every_flow_table_is_readable_by_a_member(self, seeded, table):
        rows = await _as_user(seeded, seeded["users"]["member"], f"SELECT 1 FROM {table} WHERE group_id = :g", g=seeded["group"])
        assert rows, f"{table} is invisible to a member of its own group"

    @pytest.mark.asyncio
    async def test_a_member_sees_every_seats_split_not_only_their_own(self, seeded):
        # V5's shape applied to the flow half: a shared expense is seen in full or not at all. Showing
        # each member only their own share would make "who owes whom" unanswerable.
        rows = await _as_user(
            seeded, seeded["users"]["member"], "SELECT member_id FROM shared_expense_splits WHERE shared_expense_id = :e", e=seeded["expense"]
        )
        assert len(rows) == 3


class TestAnOutsiderSeesNothing:
    @pytest.mark.parametrize("table", _FLOW_TABLES)
    @pytest.mark.asyncio
    async def test_every_flow_table_is_invisible_outside_the_group(self, seeded, table):
        rows = await _as_user(seeded, seeded["users"]["outsider"], f"SELECT 1 FROM {table} WHERE group_id = :g", g=seeded["group"])
        assert rows == [], f"{table} leaked to a user who is in no group"

    @pytest.mark.asyncio
    async def test_a_context_less_session_sees_nothing_either(self, seeded):
        # app_current_user_id() returns NULL with no GUC set, so the membership EXISTS finds nothing
        # and every group reads as empty. Fail-closed, the same posture as the owner match.
        async with seeded["app"]() as s:
            rows = (await s.execute(text("SELECT 1 FROM shared_expenses"))).all()
        assert rows == []

    @pytest.mark.parametrize("table", _FLOW_TABLES)
    @pytest.mark.asyncio
    async def test_an_outsider_cannot_write_into_a_group(self, seeded, table):
        # WITH CHECK on the new row, so a row cannot be inserted into a group the writer is not in.
        inserts = {
            "group_money_settings": "INSERT INTO group_money_settings (group_id) VALUES (:g)",
            "shared_expenses": (
                "INSERT INTO shared_expenses (group_id, date, amount, currency, split_method) VALUES (:g, '2026-06-01', 1, 'ARS', 'equal')"
            ),
            "shared_expense_splits": ("INSERT INTO shared_expense_splits (shared_expense_id, group_id, member_id, amount) VALUES (:e, :g, :m, 1)"),
            "group_settlements": (
                "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency)"
                " VALUES (:g, :f, :t, '2026-06-01', 1, 'ARS')"
            ),
        }
        params = {
            "g": seeded["group"],
            "e": seeded["expense"],
            "m": seeded["seats"]["payer"],
            "f": seeded["seats"]["payer"],
            "t": seeded["seats"]["member"],
        }
        async with seeded["app"]() as s:
            set_session_user(s, seeded["users"]["outsider"])
            with pytest.raises(DBAPIError):
                await s.execute(text(inserts[table]), params)


class TestTheAccountLegBranch:
    """What a FORMER member can still reach, and what they cannot.

    The branch exists for one reason: a shared expense funded from their own account, or a settlement
    moving through it, is a movement in THEIR ledger. Without it the row disappears from their balance
    query the moment their seat is deactivated, and the account silently gains back money it no longer
    holds. So the branch has to be exactly as wide as that and no wider.
    """

    @pytest_asyncio.fixture
    async def departed(self, seeded):
        async with seeded["admin"]() as s:
            await s.execute(text("UPDATE group_members SET is_active = FALSE WHERE id = :m"), {"m": seeded["seats"]["leaver"]})
            await s.commit()
        return seeded

    @pytest.mark.asyncio
    async def test_a_former_member_still_sees_the_expense_their_own_account_funded(self, departed):
        rows = await _as_user(departed, departed["users"]["leaver"], "SELECT id FROM shared_expenses WHERE id = :e", e=departed["leaver_expense"])
        assert rows, "a former member's own account funded this, and losing it would corrupt their balance"

    @pytest.mark.asyncio
    async def test_a_former_member_still_sees_the_settlement_their_own_account_paid(self, departed):
        rows = await _as_user(departed, departed["users"]["leaver"], "SELECT id FROM group_settlements WHERE id = :s", s=departed["settlement"])
        assert rows

    @pytest.mark.asyncio
    async def test_the_branch_is_no_wider_than_that(self, departed):
        # The group's OTHER expense named somebody else's account, so nothing in the branch matches it.
        rows = await _as_user(departed, departed["users"]["leaver"], "SELECT id FROM shared_expenses WHERE id = :e", e=departed["expense"])
        assert rows == []

    @pytest.mark.asyncio
    async def test_a_former_member_loses_the_splits_entirely(self, departed):
        # Splits get no branch on purpose: they name no account and move no balance, so nothing goes
        # silently wrong when they stop being visible. Leaving a group removes its expenses from your
        # own /expenses list, which is what leaving already does to a pot.
        rows = await _as_user(departed, departed["users"]["leaver"], "SELECT id FROM shared_expense_splits WHERE group_id = :g", g=departed["group"])
        assert rows == []

    @pytest.mark.asyncio
    async def test_a_former_member_cannot_delete_the_row_they_can_still_see(self, departed):
        # Postgres has NO WITH CHECK for DELETE, which is why reading is FOR SELECT and every write
        # command is FOR ALL on membership alone. Collapsing them into one policy would let this
        # succeed — the row would be gone for the whole group.
        async with departed["app"]() as s:
            set_session_user(s, departed["users"]["leaver"])
            await s.execute(text("DELETE FROM shared_expenses WHERE id = :e"), {"e": departed["leaver_expense"]})
            await s.commit()
        async with departed["admin"]() as s:
            still_there = (await s.execute(text("SELECT id FROM shared_expenses WHERE id = :e"), {"e": departed["leaver_expense"]})).all()
        assert still_there, "a former member deleted a row they could only read through the account branch"

    @pytest.mark.asyncio
    async def test_an_outsider_gets_no_branch_at_all(self, departed):
        # The branch matches an account the CALLER owns, so it can never widen anything for someone
        # who owns none of them.
        rows = await _as_user(departed, departed["users"]["outsider"], "SELECT id FROM shared_expenses WHERE id = :e", e=departed["leaver_expense"])
        assert rows == []
