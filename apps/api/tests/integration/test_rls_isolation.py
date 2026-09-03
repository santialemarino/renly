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
from app.models.group import GroupKind
from app.models.user import User
from app.repositories import push_subscription_repository
from app.services import group_service

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
    # The notification layer's two wholly-user-owned tables. `notifications` is deliberately NOT here:
    # it carries per-command policies and no INSERT policy at all, so it cannot answer the
    # cross-user-insert question the same way — see TestTheNotificationFeed.
    "notification_preferences",
    "push_subscriptions",
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
            # The notification layer, one row of each per user. The notification is written by the OWNER
            # role here because that is the only role that can write one at all — which is itself the
            # property TestTheNotificationFeed asserts.
            await s.execute(
                text("INSERT INTO notification_preferences (user_id, event, channel, enabled) VALUES (:u, 'member_joined', 'email', TRUE)"),
                {"u": uid},
            )
            await s.execute(
                text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, :e, 'p', 'a')"),
                {"u": uid, "e": f"https://push.test/{key}"},
            )
            notification = (
                await s.execute(
                    text("INSERT INTO notifications (user_id, event, payload) VALUES (:u, 'member_joined', '{}'::jsonb) RETURNING id"),
                    {"u": uid},
                )
            ).scalar_one()
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
                "notification": notification,
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
        for table in _OWNER_MATCH_TABLES + _GROUP_TABLES + ("investment_collection_members", "notifications"):
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


# The bootstrap decision, which nothing else covers: creating a group writes the very membership row
# the policy reads, so it CANNOT run on the request session — the router hands it the privileged one.
# That is a wiring choice with no other guard: switch the router to SessionDep and every unit test still
# passes while the feature 500s in production. Verified to red exactly when the bootstrap stops needing
# privilege — weakening ONE of the two WITH CHECKs still leaves the other refusing, and weakening both
# makes this test fail. PR 3's pot creation has the identical shape.
@pytest.mark.asyncio
async def test_creating_a_group_requires_the_privileged_session(seeded):
    a = seeded["ids"]["a"]
    user = User(id=a["user"], name="A", email=_EMAIL_A, password_hash="h")

    # On the restricted request role the group INSERT cannot satisfy its own WITH CHECK.
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        with pytest.raises(DBAPIError):
            await group_service.create_group(s, user, name="rls_group_boot", kind=GroupKind.trip)

    # On the owner session it succeeds, and the creator comes back as its admin.
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            response = await group_service.create_group(owner, user, name="rls_group_boot", kind=GroupKind.trip)
            assert response.my_role.value == "admin"
            assert response.active_member_count == 1
            # And the row really is readable by its creator through the request session afterwards.
            async with seeded["sessionmaker"]() as s:
                set_session_user(s, a["user"])
                visible = (await s.execute(text("SELECT count(*) FROM groups WHERE id = :g"), {"g": response.id})).scalar_one()
                assert visible == 1
            await owner.execute(text("DELETE FROM groups WHERE id = :g"), {"g": response.id})
            await owner.commit()
    finally:
        await admin_engine.dispose()


# --- The notification layer ----------------------------------------------------------------------
#
# All three tables are USER-owned rather than group-scoped, and that is the point worth proving: group
# activity is what produces a notification, but the row belongs to its recipient, so app_is_group_member
# appears in none of these policies. `notifications` additionally carries per-command policies with NO
# INSERT policy at all, which is the one property in this PR that a unit test cannot observe — a mocked
# session inserts whatever it is asked to.


# The feed's read side is a plain owner match: A sees A's rows, B's are invisible even by primary key.
@pytest.mark.asyncio
async def test_a_notification_is_visible_only_to_its_recipient(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        owners = (await s.execute(text("SELECT DISTINCT user_id FROM notifications"))).scalars().all()
        assert owners == [a["user"]]
        assert (await s.execute(text("SELECT count(*) FROM notifications WHERE id = :i"), {"i": b["notification"]})).scalar_one() == 0


# The load-bearing one. Fanning an event out writes a row per RECIPIENT, which a
# `user_id = app_current_user_id()` WITH CHECK could never permit — so `notifications` has no INSERT
# policy, the dispatcher runs on the privileged session, and NOBODY can write into a feed through a
# request connection. Including their own: a user who could insert their own notifications could forge
# a record of something that never happened.
@pytest.mark.asyncio
async def test_nobody_can_insert_a_notification_through_a_request_connection(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        with pytest.raises(DBAPIError):
            await s.execute(
                text("INSERT INTO notifications (user_id, event, payload) VALUES (:u, 'member_joined', '{}'::jsonb)"),
                {"u": a["user"]},
            )
            await s.commit()
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        with pytest.raises(DBAPIError):
            await s.execute(
                text("INSERT INTO notifications (user_id, event, payload) VALUES (:u, 'member_joined', '{}'::jsonb)"),
                {"u": b["user"]},
            )
            await s.commit()
    # And the owner role still can, or the fan-out would not work at all — which is what makes the two
    # refusals above evidence of a policy rather than of a broken table.
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            inserted = (
                await owner.execute(
                    text("INSERT INTO notifications (user_id, event, payload) VALUES (:u, 'member_joined', '{}'::jsonb) RETURNING id"),
                    {"u": a["user"]},
                )
            ).scalar_one()
            await owner.execute(text("DELETE FROM notifications WHERE id = :i"), {"i": inserted})
            await owner.commit()
    finally:
        await admin_engine.dispose()


# Marking one read is allowed; re-addressing it to somebody else is not.
#
# TWO independent mechanisms hold the second half, which is worth knowing before anyone "simplifies"
# either: the UPDATE policy's WITH CHECK, and Postgres additionally requiring an updated row to stay
# visible under the SELECT policy. Widening either one alone still refuses it — verified by mutating
# each in turn against this database — so this asserts the PROPERTY rather than one policy, and the
# WITH CHECK is what keeps integrity from depending on the confidentiality policy staying narrow.
@pytest.mark.asyncio
async def test_a_recipient_may_mark_their_own_read_but_not_re_address_it(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        await s.execute(text("UPDATE notifications SET read_at = NOW() WHERE id = :i"), {"i": a["notification"]})
        await s.commit()
        set_session_user(s, a["user"])
        assert (await s.execute(text("SELECT read_at IS NOT NULL FROM notifications WHERE id = :i"), {"i": a["notification"]})).scalar_one() is True
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE notifications SET user_id = :b WHERE id = :i"), {"b": b["user"], "i": a["notification"]})
            await s.commit()


# DELETE has its own policy because Postgres has no WITH CHECK for it: a single FOR ALL policy would
# have needed one and could not have had it. A recipient may drop their own row and nobody else's.
#
# The second half is asserted by a row COUNT rather than by an error, because a DELETE that matches
# nothing succeeds silently — and it is the SELECT policy that makes it match nothing, since A cannot
# see B's row to delete it. The DELETE policy's own job is the FIRST half: without it, a recipient
# could not dismiss their own notification at all (mutated both ways to confirm each).
@pytest.mark.asyncio
async def test_a_recipient_may_delete_their_own_notification_and_no_other(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        await s.execute(text("DELETE FROM notifications WHERE id = :i"), {"i": b["notification"]})
        await s.commit()
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            survived = (await owner.execute(text("SELECT count(*) FROM notifications WHERE id = :i"), {"i": b["notification"]})).scalar_one()
            assert survived == 1, "A deleted B's notification"
    finally:
        await admin_engine.dispose()
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        await s.execute(text("DELETE FROM notifications WHERE id = :i"), {"i": a["notification"]})
        await s.commit()
        set_session_user(s, a["user"])
        assert (await s.execute(text("SELECT count(*) FROM notifications"))).scalar_one() == 0


# A push subscription holds the keys a payload is sealed with, so the confidentiality boundary matters
# more here than on an ordinary preferences row: anybody who could read another user's would be able to
# push to that person's browser as if they were Renly.
@pytest.mark.asyncio
async def test_a_push_subscription_is_never_readable_by_another_account(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, a["user"])
        endpoints = (await s.execute(text("SELECT endpoint FROM push_subscriptions"))).scalars().all()
        assert endpoints == ["https://push.test/a"]
        assert (await s.execute(text("SELECT count(*) FROM push_subscriptions WHERE user_id = :u"), {"u": b["user"]})).scalar_one() == 0


# A browser holds ONE push subscription, so when a second account signs in on a shared computer and
# enables push, the endpoint it presents is the one the FIRST account is registered under.
#
# This is the policy fact the service is built around: the upsert's conflict target is checked against
# the owner-match USING expression, so a row belonging to somebody else does not quietly move — it
# RAISES. Which means a subscribe would 500 and, worse, the first account's row would survive and keep
# pushing their group activity to a browser somebody else is now signed in on. `release_endpoint` on the
# privileged session is what closes it, and this is the proof that it is needed rather than defensive.
@pytest.mark.asyncio
async def test_one_account_cannot_take_a_browser_from_another_through_its_own_connection(seeded):
    a, b = seeded["ids"]["a"], seeded["ids"]["b"]
    shared = "https://push.test/a"
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            await owner.execute(
                text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, 'https://push.test/other', 'p', 'a')"),
                {"u": a["user"]},
            )
            await owner.commit()
    finally:
        await admin_engine.dispose()
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, b["user"])
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, :e, 'p2', 'a2') "
                    "ON CONFLICT ON CONSTRAINT push_subscriptions_endpoint_once "
                    "DO UPDATE SET user_id = EXCLUDED.user_id, p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth"
                ),
                {"u": b["user"], "e": shared},
            )
            await s.commit()
    # A's row is untouched, which is the half that would be a disclosure rather than an error.
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            still = (await owner.execute(text("SELECT user_id FROM push_subscriptions WHERE endpoint = :e"), {"e": shared})).scalar_one()
            assert still == a["user"]
            # And the privileged release is what the service uses to hand the browser over. The real
            # repository function, not a restatement of it: what it deletes and what it spares is the
            # thing under test, and an inlined DELETE here would be a second opinion that stays green
            # while the one the service calls drifts.
            await push_subscription_repository.release_endpoint(owner, shared, keep_user_id=b["user"])
            await owner.commit()
            assert (await owner.execute(text("SELECT count(*) FROM push_subscriptions WHERE endpoint = :e"), {"e": shared})).scalar_one() == 0
            # And ONLY that browser: A's phone, subscribed under a different endpoint, is not swept up
            # by B claiming A's laptop. Without the endpoint predicate the release would unsubscribe
            # every other account's every browser, and the count above would not notice.
            elsewhere = (
                await owner.execute(text("SELECT count(*) FROM push_subscriptions WHERE endpoint = :e"), {"e": "https://push.test/other"})
            ).scalar_one()
            assert elsewhere == 1, "releasing one endpoint unsubscribed a browser it was never about"
    finally:
        await admin_engine.dispose()
    async with seeded["sessionmaker"]() as s:
        set_session_user(s, b["user"])
        claimed = (
            await s.execute(
                text("INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth) VALUES (:u, :e, 'p2', 'a2') RETURNING id"),
                {"u": b["user"], "e": shared},
            )
        ).scalar_one()
        await s.commit()
        set_session_user(s, b["user"])
        assert (await s.execute(text("SELECT count(*) FROM push_subscriptions WHERE endpoint = :e"), {"e": shared})).scalar_one() == 1
    # Re-subscribing on a browser you already hold — a page reload does it — must leave the row alone.
    # `keep_user_id` is what makes the release a hand-over rather than a delete-and-recreate, which
    # would mint a new row (losing when it was registered and last used) on every visit.
    admin_engine = create_async_engine(ADMIN_URL)
    try:
        async with sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)() as owner:
            await push_subscription_repository.release_endpoint(owner, shared, keep_user_id=b["user"])
            await owner.commit()
            survivor = (await owner.execute(text("SELECT id FROM push_subscriptions WHERE endpoint = :e"), {"e": shared})).scalar_one()
            assert survivor == claimed
    finally:
        await admin_engine.dispose()


# The dedupe index is what makes a repeating notification idempotent: the same (user, event, key) twice
# is refused, a different period is a different key, and two keyless rows coexist.
#
# The last of those is NOT what the index's WHERE clause buys — NULLs are distinct in any unique index,
# so keyless rows would never collide either way (checked directly rather than assumed). It is asserted
# anyway because it is the behaviour every one-off notification depends on, and the uniqueness IS
# load-bearing: without it the hourly reminder writes a row every hour.
@pytest.mark.asyncio
async def test_the_dedupe_index_binds_only_the_rows_that_opt_into_it(seeded):
    a = seeded["ids"]["a"]
    admin_engine = create_async_engine(ADMIN_URL)
    insert = text("INSERT INTO notifications (user_id, event, payload, dedupe_key) VALUES (:u, 'snapshot_due', '{}'::jsonb, :k) RETURNING id")
    try:
        session_factory = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)
        async with session_factory() as owner:
            first = (await owner.execute(insert, {"u": a["user"], "k": "pot:1:2026-09"})).scalar_one()
            await owner.commit()
        # The same key again is refused.
        async with session_factory() as owner:
            with pytest.raises(DBAPIError):
                await owner.execute(insert, {"u": a["user"], "k": "pot:1:2026-09"})
                await owner.commit()
        # A different period is a different key, so the next month's reminder still lands.
        async with session_factory() as owner:
            second = (await owner.execute(insert, {"u": a["user"], "k": "pot:1:2026-10"})).scalar_one()
            # And two keyless rows of the same event coexist, which the partial WHERE is what allows.
            third = (await owner.execute(insert, {"u": a["user"], "k": None})).scalar_one()
            fourth = (await owner.execute(insert, {"u": a["user"], "k": None})).scalar_one()
            await owner.commit()
            await owner.execute(text("DELETE FROM notifications WHERE id = ANY(:ids)"), {"ids": [first, second, third, fourth]})
            await owner.commit()
    finally:
        await admin_engine.dispose()
