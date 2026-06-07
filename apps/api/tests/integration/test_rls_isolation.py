import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Database-layer proof of Row-Level Security (SEC-15). Unlike the rest of the suite these tests
# need a real Postgres with the RLS schema applied AND two roles: the restricted request role
# (RLS_TEST_DATABASE_URL) and the table owner (RLS_TEST_ADMIN_DATABASE_URL). They are skipped when
# those env vars are absent, so the default unit-only `pnpm test:api` run stays green. Importing
# app.db registers the after_begin listener that re-applies the per-transaction user GUC, so these
# tests exercise the real isolation mechanism, not a reimplementation.
from app.db import set_session_user

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAIL_A = "rls_user_a@test.local"
_EMAIL_B = "rls_user_b@test.local"

# Every user-owned table whose policy is a direct user_id (or, for users, id) owner-match.
_OWNER_MATCH_TABLES = (
    "users",
    "investments",
    "investment_snapshots",
    "transactions",
    "investment_groups",
    "credit_cards",
    "income_entries",
    "card_settlements",
    "subscriptions",
    "installments",
    "expense_entries",
    "card_reconciliations",
    "payment_obligations",
    "api_keys",
    "user_settings",
)


# Seeds two fully-populated users via the owner role, yields their ids + a restricted-role session
# factory, then deletes both users (cascading their rows) and disposes the engines.
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app_sessionmaker = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

    admin_sessionmaker = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)
    async with admin_sessionmaker() as s:
        await s.execute(text("DELETE FROM users WHERE email IN (:a, :b)"), {"a": _EMAIL_A, "b": _EMAIL_B})
        ids = {}
        for key, email in (("a", _EMAIL_A), ("b", _EMAIL_B)):
            uid = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"),
                    {"n": key.upper(), "e": email},
                )
            ).scalar_one()
            inv = (
                await s.execute(
                    text("INSERT INTO investments (user_id, name, category, base_currency) VALUES (:u, 'inv', 'stocks', 'USD') RETURNING id"),
                    {"u": uid},
                )
            ).scalar_one()
            card = (
                await s.execute(
                    text("INSERT INTO credit_cards (user_id, name, closing_day, due_day, currency) VALUES (:u, 'card', 1, 10, 'USD') RETURNING id"),
                    {"u": uid},
                )
            ).scalar_one()
            grp = (
                await s.execute(
                    text("INSERT INTO investment_groups (user_id, name) VALUES (:u, 'grp') RETURNING id"),
                    {"u": uid},
                )
            ).scalar_one()
            await s.execute(
                text("INSERT INTO investment_snapshots (investment_id, user_id, date, value, currency) VALUES (:i, :u, '2026-01-01', 100, 'USD')"),
                {"i": inv, "u": uid},
            )
            await s.execute(
                text(
                    "INSERT INTO transactions (investment_id, user_id, date, amount, currency, type) VALUES (:i, :u, '2026-01-01', 50, 'USD', 'buy')"
                ),
                {"i": inv, "u": uid},
            )
            await s.execute(
                text("INSERT INTO card_settlements (credit_card_id, user_id, date, amount, currency) VALUES (:c, :u, '2026-01-01', 5, 'USD')"),
                {"c": card, "u": uid},
            )
            await s.execute(
                text("INSERT INTO investment_group_members (investment_id, group_id) VALUES (:i, :g)"),
                {"i": inv, "g": grp},
            )
            ids[key] = {"user": uid, "investment": inv, "card": card, "group": grp}
        await s.commit()

    try:
        yield {"sessionmaker": app_sessionmaker, "ids": ids}
    finally:
        async with admin_sessionmaker() as s:
            await s.execute(text("DELETE FROM users WHERE email IN (:a, :b)"), {"a": _EMAIL_A, "b": _EMAIL_B})
            await s.commit()
        await app_engine.dispose()
        await admin_engine.dispose()


# A connection with no user context set must read zero rows from every RLS-protected table — the
# GUC helper returns NULL so no row satisfies any policy. This is the "forgot to set context" floor.
@pytest.mark.asyncio
async def test_no_context_reads_no_rows(seeded):
    async with seeded["sessionmaker"]() as s:
        for table in _OWNER_MATCH_TABLES + ("investment_group_members",):
            count = (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608 (fixed table list)
            assert count == 0, f"{table} leaked {count} rows with no user context set"


# With user A's context, A sees exactly its own rows across every table shape — direct user_id, the
# users self-policy, and the EXISTS-join junction — and none of user B's.
@pytest.mark.asyncio
async def test_user_sees_only_own_rows(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])

        users = (await s.execute(text("SELECT id FROM users ORDER BY id"))).scalars().all()
        assert users == [a["user"]]

        invs = (await s.execute(text("SELECT user_id FROM investments"))).scalars().all()
        assert invs == [a["user"]]

        for table in ("investment_snapshots", "transactions", "card_settlements"):
            owners = (await s.execute(text(f"SELECT DISTINCT user_id FROM {table}"))).scalars().all()  # noqa: S608
            assert owners == [a["user"]], f"{table} exposed rows for another user: {owners}"

        members = (await s.execute(text("SELECT investment_id FROM investment_group_members"))).scalars().all()
        assert members == [a["investment"]]

        # B's specific rows are invisible to A even when addressed by primary key.
        assert (await s.execute(text("SELECT count(*) FROM investments WHERE id = :i"), {"i": b["investment"]})).scalar_one() == 0
        assert (await s.execute(text("SELECT count(*) FROM users WHERE id = :i"), {"i": b["user"]})).scalar_one() == 0


# WITH CHECK must block writing a row owned by another user, even though the owner column is set
# explicitly — the policy is enforced on INSERT, not just SELECT.
@pytest.mark.asyncio
async def test_with_check_blocks_cross_user_insert(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        with pytest.raises(DBAPIError):
            await s.execute(
                text("INSERT INTO investments (user_id, name, category, base_currency) VALUES (:u, 'evil', 'stocks', 'USD')"),
                {"u": b["user"]},
            )
            await s.commit()


# The per-transaction GUC must survive a mid-request COMMIT: services commit and then refresh/read,
# and SET LOCAL is cleared on commit, so the after_begin listener must re-establish it. Without that
# the post-commit read would silently return nothing.
@pytest.mark.asyncio
async def test_context_survives_commit(seeded):
    a = seeded["ids"]["a"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        before = (await s.execute(text("SELECT count(*) FROM investments"))).scalar_one()
        assert before == 1
        await s.execute(text("UPDATE investments SET name = 'renamed' WHERE user_id = :u"), {"u": a["user"]})
        await s.commit()  # clears SET LOCAL; the next read runs in a brand-new transaction
        after = (await s.execute(text("SELECT count(*) FROM investments"))).scalar_one()
        assert after == 1, "user context was lost after commit — after_begin did not re-apply the GUC"
