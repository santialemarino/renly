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
# A third account that joins A's group, so "a member sees the group" and "a non-member sees nothing"
# are proven by different people rather than by the group's own creator.
_EMAIL_C = "rls_user_c@test.local"
# A fourth account that joins nothing at all — the "logged in, belongs to no group" case, which is
# every existing Renly user the moment these tables ship.
_EMAIL_D = "rls_user_d@test.local"

# Every user-owned table whose policy is a direct user_id (or, for users, id) owner-match.
_OWNER_MATCH_TABLES = (
    "users",
    "investments",
    "investment_snapshots",
    "transactions",
    "investment_collections",
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

# The group tables, whose policy is the membership EXISTS-join through app_is_group_member() rather
# than an owner match. Listed separately because the questions they must answer are different: not
# "is this row mine" but "am I an active member of the group this row belongs to".
_GROUP_TABLES = (
    "groups",
    "group_members",
    "group_invites",
)


# Seeds three users via the owner role — A and B fully populated and unrelated, plus C, who holds a
# seat in A's group so membership can be proven by someone other than the group's creator. Yields
# their ids + a restricted-role session factory, then deletes all three (cascading their rows) and
# disposes the engines. A's group also carries a name-only placeholder seat and an outstanding invite,
# so the roster read covers both a linked and an unlinked member.
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app_sessionmaker = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)

    admin_sessionmaker = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)
    async with admin_sessionmaker() as s:
        await s.execute(text("DELETE FROM users WHERE email IN (:a, :b, :c, :d)"), {"a": _EMAIL_A, "b": _EMAIL_B, "c": _EMAIL_C, "d": _EMAIL_D})
        # groups are not FK'd to a single owner, so deleting the users does not cascade them away —
        # created_by is ON DELETE SET NULL by design. Clear them by name instead.
        await s.execute(text("DELETE FROM groups WHERE name IN ('rls_group_a', 'rls_group_b')"))
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
            coll = (
                await s.execute(
                    text("INSERT INTO investment_collections (user_id, name) VALUES (:u, 'coll') RETURNING id"),
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
                text("INSERT INTO investment_collection_members (investment_id, collection_id) VALUES (:i, :c)"),
                {"i": inv, "c": coll},
            )
            group = (
                await s.execute(
                    text("INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id"),
                    {"n": f"rls_group_{key}", "u": uid},
                )
            ).scalar_one()
            own_seat = (
                await s.execute(
                    text("INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, 'owner seat', 'admin') RETURNING id"),
                    {"g": group, "u": uid},
                )
            ).scalar_one()
            # A name-only placeholder: no user_id at all, so a policy keyed on the row's own user_id
            # (rather than on the group) would hide it from every member including the admin.
            placeholder = (
                await s.execute(
                    text("INSERT INTO group_members (group_id, display_name) VALUES (:g, 'placeholder seat') RETURNING id"),
                    {"g": group},
                )
            ).scalar_one()
            await s.execute(
                text(
                    "INSERT INTO group_invites (group_id, member_id, email, token_hash, expires_at, created_by) "
                    "VALUES (:g, :m, :e, :h, NOW() AT TIME ZONE 'utc' + INTERVAL '7 days', :u)"
                ),
                {"g": group, "m": placeholder, "e": f"invitee_{key}@test.local", "h": f"hash_{key}", "u": uid},
            )
            ids[key] = {
                "user": uid,
                "investment": inv,
                "card": card,
                "collection": coll,
                "group": group,
                "own_seat": own_seat,
                "placeholder": placeholder,
            }

        # C exists but joins nothing yet — the non-member baseline — and then takes a seat in A's group
        # so the member-side assertions are made by a user who did not create it.
        c_uid = (
            await s.execute(
                text("INSERT INTO users (name, email, password_hash) VALUES ('C', :e, 'h') RETURNING id"),
                {"e": _EMAIL_C},
            )
        ).scalar_one()
        c_seat = (
            await s.execute(
                text("INSERT INTO group_members (group_id, user_id, display_name) VALUES (:g, :u, 'C seat') RETURNING id"),
                {"g": ids["a"]["group"], "u": c_uid},
            )
        ).scalar_one()
        ids["c"] = {"user": c_uid, "seat": c_seat}
        d_uid = (
            await s.execute(
                text("INSERT INTO users (name, email, password_hash) VALUES ('D', :e, 'h') RETURNING id"),
                {"e": _EMAIL_D},
            )
        ).scalar_one()
        ids["d"] = {"user": d_uid}
        await s.commit()

    try:
        yield {"sessionmaker": app_sessionmaker, "ids": ids}
    finally:
        async with admin_sessionmaker() as s:
            await s.execute(text("DELETE FROM groups WHERE name IN ('rls_group_a', 'rls_group_b')"))
            await s.execute(text("DELETE FROM users WHERE email IN (:a, :b, :c, :d)"), {"a": _EMAIL_A, "b": _EMAIL_B, "c": _EMAIL_C, "d": _EMAIL_D})
            await s.commit()
        await app_engine.dispose()
        await admin_engine.dispose()


# A connection with no user context set must read zero rows from every RLS-protected table — the
# GUC helper returns NULL so no row satisfies any policy. This is the "forgot to set context" floor.
@pytest.mark.asyncio
async def test_no_context_reads_no_rows(seeded):
    async with seeded["sessionmaker"]() as s:
        for table in _OWNER_MATCH_TABLES + _GROUP_TABLES + ("investment_collection_members",):
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

        members = (await s.execute(text("SELECT investment_id FROM investment_collection_members"))).scalars().all()
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


# --- Group membership policies (shared money) ---------------------------------------------------
#
# The mandatory §7 matrix, per table: a non-member reads nothing, and a member reads only their own
# groups' rows. These need a real database because the predicate is not "is this row mine" — it is an
# EXISTS-join through app_is_group_member(), and a mocked session cannot notice a policy that has
# stopped joining correctly (or one that recurses, which a self-referencing predicate on group_members
# does: Postgres aborts it outright).


# A member of one group sees its rows and NONE of another group's — the ordinary isolation case. B
# legitimately sees B's own group, which is what makes the zero counts for A's rows meaningful: the
# policy is filtering, not simply denying everything.
@pytest.mark.asyncio
async def test_a_member_of_one_group_sees_nothing_of_another(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, b["user"])
        assert (await s.execute(text("SELECT id FROM groups"))).scalars().all() == [b["group"]]
        for table in ("group_members", "group_invites"):
            leaked = (
                await s.execute(text(f"SELECT count(*) FROM {table} WHERE group_id = :g"), {"g": a["group"]})  # noqa: S608 (fixed table list)
            ).scalar_one()
            assert leaked == 0, f"{table} leaked {leaked} of A's rows to B"
            own = (
                await s.execute(text(f"SELECT count(*) FROM {table} WHERE group_id = :g"), {"g": b["group"]})  # noqa: S608 (fixed table list)
            ).scalar_one()
            assert own > 0, f"{table} hid B's own rows, so the zero above proves nothing"


# A logged-in user who belongs to no group reads zero rows from every group table — not "their own, of
# which there are none", but nothing whatsoever. A predicate that accidentally passed for everyone
# would show up here and nowhere else.
@pytest.mark.asyncio
async def test_a_user_in_no_group_sees_nothing_at_all(seeded):
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, seeded["ids"]["d"]["user"])
        for table in _GROUP_TABLES:
            count = (await s.execute(text(f"SELECT count(*) FROM {table}"))).scalar_one()  # noqa: S608 (fixed table list)
            assert count == 0, f"{table} exposed {count} rows to a user who belongs to no group"


# A member sees their group and its whole roster — including the name-only placeholder, which has no
# user_id of its own. Keying the policy on the row's user_id instead of the group would hide it.
@pytest.mark.asyncio
async def test_member_sees_the_whole_roster_including_placeholders(seeded):
    a, c = seeded["ids"]["a"], seeded["ids"]["c"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, c["user"])
        groups = (await s.execute(text("SELECT id FROM groups"))).scalars().all()
        assert groups == [a["group"]], "C must see A's group and no other"
        seats = (await s.execute(text("SELECT id FROM group_members ORDER BY id"))).scalars().all()
        assert seats == sorted([a["own_seat"], a["placeholder"], c["seat"]])
        # The invite belongs to a seat that is not C's, and C still sees it — invites are group state.
        invites = (await s.execute(text("SELECT member_id FROM group_invites"))).scalars().all()
        assert invites == [a["placeholder"]]


# Deactivating a seat revokes access in the same statement that removes the person: is_active lives
# inside the policy predicate, so there is no second place to remember.
@pytest.mark.asyncio
async def test_deactivating_a_seat_revokes_access_immediately(seeded):
    a, c = seeded["ids"]["a"], seeded["ids"]["c"]
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            await owner.execute(text("UPDATE group_members SET is_active = FALSE WHERE id = :m"), {"m": c["seat"]})
            await owner.commit()
        async with seeded["sessionmaker"]() as s:
            set_session_user(s, c["user"])
            assert (await s.execute(text("SELECT count(*) FROM groups WHERE id = :g"), {"g": a["group"]})).scalar_one() == 0
            assert (await s.execute(text("SELECT count(*) FROM group_members"))).scalar_one() == 0
            assert (await s.execute(text("SELECT count(*) FROM group_invites"))).scalar_one() == 0
    finally:
        await admin_engine.dispose()


# WITH CHECK must block writing into a group you do not belong to, even with the group_id set
# explicitly — the policy is enforced on INSERT, not just SELECT.
@pytest.mark.asyncio
async def test_with_check_blocks_writing_into_another_groups_rows(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, b["user"])
        with pytest.raises(DBAPIError):
            await s.execute(
                text("INSERT INTO group_members (group_id, display_name) VALUES (:g, 'intruder')"),
                {"g": a["group"]},
            )
            await s.commit()


# The membership helper answers only about the CALLING user, for any argument. A non-member asking
# about someone else's group gets false rather than an answer derived from that group's rows.
@pytest.mark.asyncio
async def test_membership_helper_answers_only_about_the_caller(seeded):
    a, b, c = seeded["ids"]["a"], seeded["ids"]["b"], seeded["ids"]["c"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, c["user"])
        assert (await s.execute(text("SELECT app_is_group_member(:g)"), {"g": a["group"]})).scalar_one() is True
        assert (await s.execute(text("SELECT app_is_group_member(:g)"), {"g": b["group"]})).scalar_one() is False
    async with seeded["sessionmaker"]() as s:
        # No user context at all: fails closed, exactly like the owner-match policies.
        assert (await s.execute(text("SELECT app_is_group_member(:g)"), {"g": a["group"]})).scalar_one() is False
