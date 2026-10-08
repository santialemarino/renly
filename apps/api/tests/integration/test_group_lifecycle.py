import asyncio
import hashlib
import os
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Database-layer proof of the group cleanup that runs on account deletion. This needs a real Postgres
# for a reason a mocked session cannot cover: `list_orphaned_group_ids` is a correlated EXISTS /
# NOT EXISTS pair, and it decides what gets DELETED — the one query in this PR whose wrong answer
# destroys a live group instead of merely hiding one. It runs on the owner (privileged) connection,
# because a group is reachable only through membership and the deleting user's seat may not be active.
from app.domain import InvalidTokenError
from app.models.user import User
from app.repositories import group_repository
from app.services import group_invite_service, pot_service

ADMIN_URL = os.getenv("GROUPS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not ADMIN_URL,
    reason="set GROUPS_TEST_DATABASE_URL (a real Postgres with the schema applied) to run these",
)

_EMAILS = ("grp_me@test.local", "grp_other@test.local", "grp_third@test.local")


# Yields an owner-role session factory plus a seeder, and clears every row it created afterwards.
# Groups are cleared by name rather than by cascade: created_by is ON DELETE SET NULL by design, so
# deleting the users does not take their groups with them — which is the very behaviour under test.
# A group's pots refuse to go while anything still names them (every pot_id foreign key is RESTRICT),
# so the holdings their pots still hold go first, then the users (taking every private holding and its
# history with them, including any history a failed absorption left naming a pot), then the groups.
@pytest_asyncio.fixture
async def db():
    engine = create_async_engine(ADMIN_URL)
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def cleanup(s: AsyncSession) -> None:
        pots = "SELECT p.id FROM pots p JOIN groups g ON g.id = p.group_id WHERE g.name LIKE 'grp\\_%'"
        await s.execute(text(f"DELETE FROM investments WHERE pot_id IN ({pots})"))  # noqa: S608 (fixed text)
        await s.execute(text(f"DELETE FROM accounts WHERE pot_id IN ({pots})"))  # noqa: S608 (fixed text)
        await s.execute(text("DELETE FROM users WHERE email IN (:a, :b, :c)"), dict(zip("abc", _EMAILS, strict=True)))
        await s.execute(text("DELETE FROM groups WHERE name LIKE 'grp\\_%'"))

    async with factory() as s:
        await cleanup(s)
        users = {}
        for key, email in zip(("me", "other", "third"), _EMAILS, strict=True):
            users[key] = (
                await s.execute(
                    text("INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id"),
                    {"n": key, "e": email},
                )
            ).scalar_one()
        await s.commit()

    try:
        yield {"factory": factory, "users": users}
    finally:
        async with factory() as s:
            await cleanup(s)
            await s.commit()
        await engine.dispose()


# Creates a group named `name` with the given seats: (user key or None for a placeholder, is_active).
async def _make_group(s: AsyncSession, users: dict, name: str, seats: list[tuple[str | None, bool]]) -> int:
    group_id = (
        await s.execute(
            text("INSERT INTO groups (name, kind) VALUES (:n, 'household') RETURNING id"),
            {"n": name},
        )
    ).scalar_one()
    for user_key, is_active in seats:
        await s.execute(
            text("INSERT INTO group_members (group_id, user_id, display_name, is_active) VALUES (:g, :u, 'seat', :a)"),
            {"g": group_id, "u": users[user_key] if user_key else None, "a": is_active},
        )
    return group_id


class TestOrphanedGroupDetection:
    @pytest.mark.asyncio
    async def test_a_group_whose_only_account_holder_leaves_is_orphaned(self, db):
        # Placeholders cannot see, administer or re-enter the group, so once the one real account goes
        # nothing can ever read or remove it again.
        users = db["users"]
        async with db["factory"]() as s:
            solo = await _make_group(s, users, "grp_solo", [("me", True), (None, True), (None, True)])
            await s.commit()
            assert await group_repository.list_orphaned_group_ids(s, users["me"]) == [solo]

    @pytest.mark.asyncio
    async def test_a_group_with_another_active_member_survives(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_shared", [("me", True), ("other", True)])
            await s.commit()
            assert await group_repository.list_orphaned_group_ids(s, users["me"]) == []

    @pytest.mark.asyncio
    async def test_another_member_who_is_no_longer_active_does_not_save_the_group(self, db):
        # A former member cannot see the group either — the membership policy requires is_active — so
        # leaving it behind for their sake would keep it exactly as unreachable.
        users = db["users"]
        async with db["factory"]() as s:
            solo = await _make_group(s, users, "grp_former", [("me", True), ("other", False)])
            await s.commit()
            assert await group_repository.list_orphaned_group_ids(s, users["me"]) == [solo]

    @pytest.mark.asyncio
    async def test_a_group_the_user_does_not_belong_to_is_never_returned(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_theirs", [("other", True), ("third", True)])
            await s.commit()
            assert await group_repository.list_orphaned_group_ids(s, users["me"]) == []

    @pytest.mark.asyncio
    async def test_someone_elses_already_unreachable_group_is_not_collected_either(self, db):
        # The case that makes the membership half of the predicate load-bearing: a group with no active
        # account-holder at all is unreachable, but it is not THIS user's to clean up. Testing only
        # against groups that still have live members would let a query that dropped the membership
        # test pass, and it would then delete strangers' groups on every account deletion.
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_stranded", [(None, True), ("other", False)])
            await s.commit()
            assert await group_repository.list_orphaned_group_ids(s, users["me"]) == []

    @pytest.mark.asyncio
    async def test_a_users_own_inactive_seat_still_counts_as_belonging(self, db):
        # They were removed but never deleted their account; the group is still unreachable once they
        # go, and nothing else would ever collect it.
        users = db["users"]
        async with db["factory"]() as s:
            solo = await _make_group(s, users, "grp_inactive_me", [("me", False), (None, True)])
            await s.commit()
            assert await group_repository.list_orphaned_group_ids(s, users["me"]) == [solo]

    @pytest.mark.asyncio
    async def test_it_returns_exactly_the_orphans_when_several_groups_exist(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            orphan_a = await _make_group(s, users, "grp_orphan_a", [("me", True), (None, True)])
            await _make_group(s, users, "grp_kept", [("me", True), ("other", True)])
            orphan_b = await _make_group(s, users, "grp_orphan_b", [("me", True)])
            await _make_group(s, users, "grp_not_mine", [("third", True)])
            await s.commit()
            assert sorted(await group_repository.list_orphaned_group_ids(s, users["me"])) == sorted([orphan_a, orphan_b])


class TestOrphanedGroupDeletion:
    @pytest.mark.asyncio
    async def test_deleting_by_id_removes_the_group_with_its_seats_and_invites(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            group_id = await _make_group(s, users, "grp_cascade", [("me", True), (None, True)])
            placeholder = (
                await s.execute(
                    text("SELECT id FROM group_members WHERE group_id = :g AND user_id IS NULL"),
                    {"g": group_id},
                )
            ).scalar_one()
            await s.execute(
                text(
                    "INSERT INTO group_invites (group_id, member_id, token_hash, expires_at) "
                    "VALUES (:g, :m, 'grp_hash', NOW() AT TIME ZONE 'utc' + INTERVAL '7 days')"
                ),
                {"g": group_id, "m": placeholder},
            )
            await s.commit()

            await group_repository.delete_by_ids(s, [group_id])
            await s.commit()
            for table in ("groups", "group_members", "group_invites"):
                column = "id" if table == "groups" else "group_id"
                remaining = (
                    await s.execute(text(f"SELECT count(*) FROM {table} WHERE {column} = :g"), {"g": group_id})  # noqa: S608 (fixed table list)
                ).scalar_one()
                assert remaining == 0, f"{table} kept {remaining} rows after the group was deleted"

    @pytest.mark.asyncio
    async def test_deleting_an_empty_id_list_touches_nothing(self, db):
        # The caller passes whatever the orphan query returned, which is usually nothing at all.
        users = db["users"]
        async with db["factory"]() as s:
            group_id = await _make_group(s, users, "grp_untouched", [("me", True)])
            await s.commit()
            await group_repository.delete_by_ids(s, [])
            await s.commit()
            assert (await s.execute(text("SELECT count(*) FROM groups WHERE id = :g"), {"g": group_id})).scalar_one() == 1


# The scope-denormalized children of each parent, as (child table, parent table, the child's foreign
# keys to it). The structural half, tests/unit/test_scope_children_follow.py, derives the same list from
# the models and pins it, so a child added there and not here fails there.
_CHILDREN = (
    ("account_reconciliations", "accounts", ("account_id",)),
    ("transfers", "accounts", ("from_account_id", "to_account_id")),
    ("investment_snapshots", "investments", ("investment_id",)),
    ("transactions", "investments", ("investment_id",)),
)


# Seeds a pot in `group_id` holding the full set of children: an account with two reconciliations, two
# accounts with a transfer between them, and an investment with two snapshots and two transactions —
# every row pot-scoped, as the services write them. Returns the pot id and its parents' ids.
async def _seed_pot(s: AsyncSession, group_id: int) -> dict:
    async def one(sql: str, **params) -> int:
        return (await s.execute(text(sql + " RETURNING id"), params)).scalar_one()

    pot = await one("INSERT INTO pots (group_id, base_currency) VALUES (:g, 'USD')", g=group_id)
    accounts = [
        await one(
            "INSERT INTO accounts (pot_id, name, type, currency, opening_date) VALUES (:p, :n, 'bank', 'USD', '2026-01-01')",
            p=pot,
            n=f"grp_acct_{i}",
        )
        for i in range(3)
    ]
    for day in ("2026-02-01", "2026-03-01"):
        await one(
            "INSERT INTO account_reconciliations (pot_id, account_id, as_of_date, statement_balance, computed_balance, difference) "
            "VALUES (:p, :a, :d, 10, 10, 0)",
            p=pot,
            a=accounts[0],
            d=date.fromisoformat(day),
        )
    await one(
        "INSERT INTO transfers (pot_id, from_account_id, to_account_id, date, from_amount, to_amount) VALUES (:p, :f, :t, '2026-02-15', 5, 5)",
        p=pot,
        f=accounts[1],
        t=accounts[2],
    )
    investment = await one("INSERT INTO investments (pot_id, name, category, base_currency) VALUES (:p, 'grp_fund', 'fci', 'USD')", p=pot)
    for day in ("2026-02-01", "2026-03-01"):
        await one(
            "INSERT INTO investment_snapshots (investment_id, pot_id, date, value, currency) VALUES (:i, :p, :d, 100, 'USD')",
            i=investment,
            p=pot,
            d=date.fromisoformat(day),
        )
        await one(
            "INSERT INTO transactions (investment_id, pot_id, date, amount, currency, type) VALUES (:i, :p, :d, 100, 'USD', 'buy')",
            i=investment,
            p=pot,
            d=date.fromisoformat(day),
        )
    return {"pot": pot, "accounts": accounts, "investments": [investment]}


# Every child row of the given parents, as (table, user_id, pot_id), whichever leg names the parent.
async def _child_scopes(s: AsyncSession, parents: dict) -> list[tuple[str, int | None, int | None]]:
    rows = []
    for child, parent, fks in _CHILDREN:
        matches = " OR ".join(f"{fk} = ANY(:ids)" for fk in fks)
        result = await s.execute(text(f"SELECT user_id, pot_id FROM {child} WHERE {matches}"), {"ids": parents[parent]})  # noqa: S608 (fixed table list)
        rows += [(child, r.user_id, r.pot_id) for r in result]
    return rows


# Every child of the given parents whose scope differs from its parent's, on any leg: the drift itself,
# asked of the database rather than of the code that is supposed to prevent it.
async def _drift(s: AsyncSession, parents: dict) -> list[tuple]:
    drifted = []
    for child, parent, fks in _CHILDREN:
        for fk in fks:
            result = await s.execute(
                text(
                    f"SELECT c.id, c.user_id, c.pot_id, p.user_id, p.pot_id FROM {child} c JOIN {parent} p ON p.id = c.{fk} "  # noqa: S608 (fixed table list)
                    "WHERE p.id = ANY(:ids) AND (c.user_id IS DISTINCT FROM p.user_id OR c.pot_id IS DISTINCT FROM p.pot_id)"
                ),
                {"ids": parents[parent]},
            )
            drifted += [(child, fk, *r) for r in result]
    return drifted


class TestAbsorbingAnOrphanedGroupsPots:
    # Account deletion re-points an orphaned group's holdings to the leaver as private. Every history row
    # of those holdings carries its own copy of the scope, which RLS reads without a join, so a parent
    # moved without its children leaves that history readable by the pot and the pot undeletable (every
    # pot_id foreign key is RESTRICT). Driven on the admin role delete_account uses, with the scope
    # trigger of 0032 live: it holds each reconciliation to its account's CURRENT scope, so a re-point
    # that moved a child before its parent is refused here rather than passing.
    async def _setup(self, db) -> tuple[int, dict, dict]:
        users = db["users"]
        async with db["factory"]() as s:
            orphan = await _make_group(s, users, "grp_absorb_orphan", [("me", True), (None, True)])
            kept = await _make_group(s, users, "grp_absorb_kept", [("me", True), ("other", True)])
            absorbed = await _seed_pot(s, orphan)
            control = await _seed_pot(s, kept)
            await s.commit()
        return orphan, absorbed, control

    @pytest.mark.asyncio
    async def test_every_child_moves_with_its_parent(self, db):
        orphan, absorbed, _ = await self._setup(db)
        me = db["users"]["me"]
        async with db["factory"]() as s:
            assert await pot_service.absorb_group_pots(s, [orphan], me) == 4
            await s.commit()
            scopes = await _child_scopes(s, absorbed)
            assert sorted({child for child, _, _ in scopes}) == sorted(child for child, _, _ in _CHILDREN), "the seed lacks a child table"
            assert [row for row in scopes if row[1:] != (me, None)] == []
            assert await _drift(s, absorbed) == []

    @pytest.mark.asyncio
    async def test_the_absorbed_pot_can_then_be_deleted(self, db):
        # The database's own proof that nothing names the pot any more: a RESTRICT foreign key from any
        # child still carrying its id would refuse the delete.
        orphan, _, _ = await self._setup(db)
        async with db["factory"]() as s:
            await pot_service.absorb_group_pots(s, [orphan], db["users"]["me"])
            await s.commit()
            await group_repository.delete_by_ids(s, [orphan])
            await s.commit()
            assert (await s.execute(text("SELECT count(*) FROM pots WHERE group_id = :g"), {"g": orphan})).scalar_one() == 0

    @pytest.mark.asyncio
    async def test_a_surviving_groups_pot_is_untouched(self, db):
        orphan, _, control = await self._setup(db)
        async with db["factory"]() as s:
            await pot_service.absorb_group_pots(s, [orphan], db["users"]["me"])
            await s.commit()
            for table in ("accounts", "investments"):
                result = await s.execute(text(f"SELECT user_id, pot_id FROM {table} WHERE id = ANY(:ids)"), {"ids": control[table]})  # noqa: S608 (fixed table list)
                assert {tuple(r) for r in result} == {(None, control["pot"])}, table
            assert {row[1:] for row in await _child_scopes(s, control)} == {(None, control["pot"])}


class TestActiveMembershipProbe:
    # `exists_active_member_by_user` decides whether the onboarding checklist's sharing step reads as
    # done, and its whole content is one WHERE clause — which a unit test cannot reach at all, since the
    # session is mocked and returns whatever it was told to. Both predicates are pinned here, because
    # each fails in a different direction: without `user_id` the step ticks for somebody else's group,
    # and without `is_active` it stays ticked on a group the user has already left and can no longer
    # even see (the membership policy requires an active seat).
    @pytest.mark.asyncio
    async def test_an_active_seat_answers_true(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_probe_active", [("me", True)])
            await s.commit()
            assert await group_repository.exists_active_member_by_user(s, users["me"]) is True

    @pytest.mark.asyncio
    async def test_a_former_seat_answers_false(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_probe_former", [("me", False)])
            await s.commit()
            assert await group_repository.exists_active_member_by_user(s, users["me"]) is False

    @pytest.mark.asyncio
    async def test_somebody_elses_group_answers_false(self, db):
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_probe_theirs", [("other", True)])
            await s.commit()
            assert await group_repository.exists_active_member_by_user(s, users["me"]) is False

    @pytest.mark.asyncio
    async def test_one_active_seat_is_enough_when_another_is_former(self, db):
        # The near-miss the LIMIT 1 makes possible: somebody who left one group and is still in another
        # must answer true, so the probe cannot be "no former seats anywhere".
        users = db["users"]
        async with db["factory"]() as s:
            await _make_group(s, users, "grp_probe_left", [("me", False)])
            await _make_group(s, users, "grp_probe_stayed", [("me", True)])
            await s.commit()
            assert await group_repository.exists_active_member_by_user(s, users["me"]) is True


class TestConcurrentInviteClaims:
    # A group invite link is deliberately SHAREABLE, so two people can open the same one at once, and
    # the claim path resolves the invite with SELECT ... FOR UPDATE for exactly that reason. This is the
    # only place that can be proven: a mocked session ignores the lock entirely, so the unit suite is
    # green either way. Verified by removing the lock — both callers then return success, the second
    # UPDATE overwrites the first, and one person holds a success response for a group they are not in.
    @pytest.mark.asyncio
    async def test_two_people_racing_one_link_produce_exactly_one_member(self, db):
        users, factory = db["users"], db["factory"]
        raw_token = "race-token-for-one-seat"
        async with factory() as s:
            group_id = await _make_group(s, users, "grp_race", [("me", True), (None, True)])
            seat = (
                await s.execute(
                    text("SELECT id FROM group_members WHERE group_id = :g AND user_id IS NULL"),
                    {"g": group_id},
                )
            ).scalar_one()
            await s.execute(
                text(
                    "INSERT INTO group_invites (group_id, member_id, token_hash, expires_at, created_by) "
                    "VALUES (:g, :m, :h, NOW() AT TIME ZONE 'utc' + INTERVAL '7 days', :u)"
                ),
                {"g": group_id, "m": seat, "h": hashlib.sha256(raw_token.encode()).hexdigest(), "u": users["me"]},
            )
            await s.commit()

        # Two DIFFERENT accounts, each on its own session, claiming the same link at the same moment.
        async def claim(user_id: int):
            async with factory() as s:
                user = User(id=user_id, name="racer", email=f"racer{user_id}@test.local", password_hash="h")
                return await group_invite_service.accept_invite(s, raw_token, user)

        outcomes = await asyncio.gather(claim(users["other"]), claim(users["third"]), return_exceptions=True)
        accepted = [o for o in outcomes if not isinstance(o, Exception)]
        refused = [o for o in outcomes if isinstance(o, Exception)]
        assert len(accepted) == 1, f"single-use was violated — both claims succeeded: {outcomes}"
        assert len(refused) == 1 and isinstance(refused[0], InvalidTokenError), refused
        assert accepted[0].member_id == seat

        async with factory() as s:
            holders = (await s.execute(text("SELECT user_id FROM group_members WHERE id = :m"), {"m": seat})).scalars().all()
            assert len(holders) == 1 and holders[0] in (users["other"], users["third"])
            consumed = (
                await s.execute(
                    text("SELECT count(*) FROM group_invites WHERE member_id = :m AND consumed_at IS NOT NULL"),
                    {"m": seat},
                )
            ).scalar_one()
            assert consumed == 1
