import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The audit trail's policy and grants, plus the one policy this unit adds to a table it did not create.
#
# Everything here lives entirely in the database and nothing above it can be substituted for it:
#
#   * `shared_audit_log`'s policy carries a SECOND branch beyond membership — `pot_id IS NULL OR
#     app_can_view_pot(pot_id)` — and it is what stops the group's activity feed stating more than the
#     pot pages themselves would. A Python filter would be a second copy of a rule the database holds.
#
#   * The table is APPEND-ONLY by GRANT rather than by trigger, and the two cascades it carries have to
#     keep working anyway. That combination cannot be checked without a real Postgres: a trigger would
#     have made deleting a group impossible, and referential actions bypassing the grant is a property
#     of the server, not of this code.
#
#   * `pot_ownership_events_counterparty_delete` is the database half of the counterparty remedy. The
#     service refuses first, so a unit test proves only the service — the policy underneath it would
#     refuse the same delete, and nothing but this file would say so.
#
# Uses the same env vars as test_rls_isolation.py so the whole RLS set runs together.
from app.db import set_session_user

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_GROUP_NAME = "audit_rls_group"
_EMAILS = {
    # Sees the pot and may write it; the actor on every seeded entry.
    "owner": "audit_rls_owner@test.local",
    # In the group, and explicitly denied view of the pot. Must read the group's entries and NONE of
    # the pot's — the disclosure this table's second policy branch exists to prevent.
    "denied": "audit_rls_denied@test.local",
    # Named as the counterparty of the seeded re-agreement, with a READ-ONLY seat on the pot.
    "counterparty": "audit_rls_counterparty@test.local",
    # In the group, sees the pot, named on nothing.
    "bystander": "audit_rls_bystander@test.local",
    # In no group at all.
    "outsider": "audit_rls_outsider@test.local",
}


# Seeds one group with five accounts of differing access, a pot with a re-agreement in its ledger, and
# two audit entries — one group-wide and one naming the pot.
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
                text("INSERT INTO groups (name, kind, created_by) VALUES (:g, 'household', :u) RETURNING id"),
                {"g": _GROUP_NAME, "u": users["owner"]},
            )
        ).scalar_one()
        seats = {}
        for key in ("owner", "denied", "counterparty", "bystander"):
            seats[key] = (
                await s.execute(
                    text(
                        "INSERT INTO group_members (group_id, user_id, display_name, role, joined_at) "
                        "VALUES (:g, :u, :n, 'member', NOW()) RETURNING id"
                    ),
                    {"g": group, "u": users[key], "n": key},
                )
            ).scalar_one()

        pot = (
            await s.execute(
                text("INSERT INTO pots (group_id, base_currency, is_default) VALUES (:g, 'USD', TRUE) RETURNING id"),
                {"g": group},
            )
        ).scalar_one()
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
            {"p": pot, "m": seats["owner"]},
        )
        # can_view FALSE, so this member is in the group and sees none of the pot.
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, FALSE, FALSE)"),
            {"p": pot, "m": seats["denied"]},
        )
        # READ-ONLY, which is the state the counterparty remedy exists for: they own part of the pot and
        # cannot write to it, because write is granted to the creator and to nobody else.
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, FALSE)"),
            {"p": pot, "m": seats["counterparty"]},
        )
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price) VALUES (:p, 'opening', '2026-01-01', :m, 100, 1)"
            ),
            {"p": pot, "m": seats["owner"]},
        )
        reagreement = (
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, counterparty_member_id, units, unit_price) "
                    "VALUES (:p, 'reagreement', '2026-02-01', :from, :to, -20, 1) RETURNING id"
                ),
                {"p": pot, "from": seats["owner"], "to": seats["counterparty"]},
            )
        ).scalar_one()
        # Recorded FOR the counterparty's own seat, and that is what makes the type narrowing testable at
        # all. A contribution by somebody else names them nowhere, so the seat check alone would refuse
        # it and the `type = 'reagreement'` clause could be deleted with every test still passing — which
        # a mutation sweep proved before this row existed. Their OWN contribution is the row that
        # separates the two clauses, and it is a realistic one: a co-owner putting money in.
        contribution = (
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, base_amount, units, unit_price) "
                    "VALUES (:p, 'contribution', '2026-03-01', :m, 10, 10, 1) RETURNING id"
                ),
                {"p": pot, "m": seats["counterparty"]},
            )
        ).scalar_one()

        group_entry = (
            await s.execute(
                text(
                    "INSERT INTO shared_audit_log (group_id, actor_user_id, entity_type, entity_id, action, payload) "
                    "VALUES (:g, :u, 'group', :g, 'created', '{}'::jsonb) RETURNING id"
                ),
                {"g": group, "u": users["owner"]},
            )
        ).scalar_one()
        pot_entry = (
            await s.execute(
                text(
                    "INSERT INTO shared_audit_log (group_id, actor_user_id, entity_type, entity_id, action, pot_id, payload) "
                    "VALUES (:g, :u, 'pot', :p, 'created', :p, '{}'::jsonb) RETURNING id"
                ),
                {"g": group, "u": users["owner"], "p": pot},
            )
        ).scalar_one()
        await s.commit()

    yield {
        "users": users,
        "seats": seats,
        "group": group,
        "pot": pot,
        "reagreement": reagreement,
        "contribution": contribution,
        "group_entry": group_entry,
        "pot_entry": pot_entry,
        "sessionmaker": app_sessionmaker,
        "admin_sessionmaker": admin_sessionmaker,
    }

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        await s.commit()
    await app_engine.dispose()
    await admin_engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    groups = f"SELECT id FROM groups WHERE name = '{_GROUP_NAME}'"
    pots = f"SELECT id FROM pots WHERE group_id IN ({groups})"
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM shared_audit_log WHERE group_id IN ({groups})"))
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"))
    await s.execute(text(f"DELETE FROM groups WHERE name = '{_GROUP_NAME}'"))
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS.values())})


# Opens a restricted-role session with the per-request user context set to one seeded user.
def _as(seeded, key: str) -> AsyncSession:
    session = seeded["sessionmaker"]()
    set_session_user(session, seeded["users"][key])
    return session


async def _visible_entries(session: AsyncSession, group_id: int) -> set[int]:
    rows = await session.execute(text("SELECT id FROM shared_audit_log WHERE group_id = :g"), {"g": group_id})
    return {row[0] for row in rows.all()}


# ---------------------------------------------------------------------------
# Who may read the trail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_non_member_reads_no_entry_at_all(seeded):
    async with _as(seeded, "outsider") as s:
        assert await _visible_entries(s, seeded["group"]) == set()


@pytest.mark.asyncio
async def test_a_member_reads_the_whole_trail(seeded):
    async with _as(seeded, "bystander") as s:
        assert await _visible_entries(s, seeded["group"]) == {seeded["group_entry"], seeded["pot_entry"]}


@pytest.mark.asyncio
async def test_a_member_denied_the_pot_reads_the_group_entry_and_not_the_pot_one(seeded):
    """The disclosure this table's second policy branch exists to prevent, proven in BOTH directions.

    Asserting only that the pot entry is hidden would pass on a policy that hid everything, and
    asserting only that the group entry is visible would pass on a policy with no pot branch at all.
    The pair is the test.
    """
    async with _as(seeded, "denied") as s:
        assert await _visible_entries(s, seeded["group"]) == {seeded["group_entry"]}


@pytest.mark.asyncio
async def test_flipping_the_pot_to_owners_hides_its_entries_from_a_member_with_no_row(seeded):
    # The same rule reached the other way: the bystander has no explicit permission row, so they see
    # the pot through its 'members' default — and lose it, and its entries, the moment that changes.
    async with _as(seeded, "bystander") as s:
        assert seeded["pot_entry"] in await _visible_entries(s, seeded["group"])

    async with seeded["admin_sessionmaker"]() as admin:
        await admin.execute(text("UPDATE pots SET visibility = 'owners' WHERE id = :p"), {"p": seeded["pot"]})
        await admin.commit()
    try:
        async with _as(seeded, "bystander") as s:
            assert await _visible_entries(s, seeded["group"]) == {seeded["group_entry"]}
    finally:
        async with seeded["admin_sessionmaker"]() as admin:
            await admin.execute(text("UPDATE pots SET visibility = 'members' WHERE id = :p"), {"p": seeded["pot"]})
            await admin.commit()


@pytest.mark.asyncio
async def test_a_deleted_pots_entries_go_dark_rather_than_becoming_group_visible(seeded):
    """The consequence of pot_id carrying no foreign key, stated rather than discovered.

    An entry has to outlive the thing it describes — a CASCADE would erase a pot's whole history at the
    exact moment somebody deleted the pot. app_can_view_pot answers false for a pot that is gone, so
    those entries become invisible to everyone instead of visible to the whole group. Fail-closed, which
    is why `pot.deleted` is the one pot entry written with a NULL pot_id.
    """
    async with seeded["admin_sessionmaker"]() as admin:
        await admin.execute(text("DELETE FROM pot_ownership_events WHERE pot_id = :p"), {"p": seeded["pot"]})
        await admin.execute(text("DELETE FROM pot_member_permissions WHERE pot_id = :p"), {"p": seeded["pot"]})
        await admin.execute(text("DELETE FROM pots WHERE id = :p"), {"p": seeded["pot"]})
        await admin.commit()

    async with _as(seeded, "owner") as s:
        assert await _visible_entries(s, seeded["group"]) == {seeded["group_entry"]}
    # And the row is still there — hidden, not deleted, which is what makes this fail-closed rather than
    # data loss. Read on the privileged session, which bypasses the policy.
    async with seeded["admin_sessionmaker"]() as admin:
        surviving = (await admin.execute(text("SELECT COUNT(*) FROM shared_audit_log WHERE id = :i"), {"i": seeded["pot_entry"]})).scalar_one()
        assert surviving == 1


# ---------------------------------------------------------------------------
# Who may write one, and what append-only means
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_member_may_write_a_group_entry(seeded):
    # The positive control for the two refusals below: without it, "the insert failed" would be true of
    # a policy that refused every insert, which is not the rule.
    async with _as(seeded, "owner") as s:
        await s.execute(
            text(
                "INSERT INTO shared_audit_log (group_id, actor_user_id, entity_type, entity_id, action, payload) "
                "VALUES (:g, :u, 'group', :g, 'updated', '{}'::jsonb)"
            ),
            {"g": seeded["group"], "u": seeded["users"]["owner"]},
        )
        await s.rollback()


@pytest.mark.asyncio
async def test_an_outsider_cannot_forge_an_entry_in_a_group_they_are_not_in(seeded):
    async with _as(seeded, "outsider") as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO shared_audit_log (group_id, actor_user_id, entity_type, entity_id, action, payload) "
                    "VALUES (:g, :u, 'group', :g, 'updated', '{}'::jsonb)"
                ),
                {"g": seeded["group"], "u": seeded["users"]["outsider"]},
            )
        await s.rollback()


@pytest.mark.asyncio
async def test_a_member_cannot_write_an_entry_naming_a_pot_they_cannot_see(seeded):
    # The WITH CHECK half of the pot branch. Without it a member could describe activity in a pot that
    # is hidden from them — and, worse, could not then read back what they had claimed.
    async with _as(seeded, "denied") as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO shared_audit_log (group_id, actor_user_id, entity_type, entity_id, action, pot_id, payload) "
                    "VALUES (:g, :u, 'pot', :p, 'updated', :p, '{}'::jsonb)"
                ),
                {"g": seeded["group"], "u": seeded["users"]["denied"], "p": seeded["pot"]},
            )
        await s.rollback()


@pytest.mark.asyncio
async def test_the_request_role_can_neither_rewrite_nor_erase_an_entry(seeded):
    """Append-only, and it is the GRANT that says so rather than the policy.

    A permission error rather than a silent no-op is the whole point of doing it this way: RLS refuses a
    write by FILTERING, so a policy-based version would report "nothing changed" and look identical to a
    row that simply did not match.
    """
    async with _as(seeded, "owner") as s:
        with pytest.raises(ProgrammingError):
            await s.execute(text("UPDATE shared_audit_log SET action = 'deleted' WHERE id = :i"), {"i": seeded["group_entry"]})
        await s.rollback()
    async with _as(seeded, "owner") as s:
        with pytest.raises(ProgrammingError):
            await s.execute(text("DELETE FROM shared_audit_log WHERE id = :i"), {"i": seeded["group_entry"]})
        await s.rollback()


@pytest.mark.asyncio
async def test_deleting_the_group_still_takes_its_trail_with_it(seeded):
    """The reason append-only is a grant and not a trigger.

    A raising BEFORE DELETE trigger would make this impossible: an FK cascade performs a real DELETE on
    the child. Referential actions run as the referencing table's OWNER, so they are exempt from both
    the revoked grant and the policy — and the trail dies with the group, losing nothing readable,
    because app_is_group_member is false for a group that no longer exists.
    """
    async with seeded["admin_sessionmaker"]() as admin:
        await admin.execute(text("DELETE FROM pot_ownership_events WHERE pot_id = :p"), {"p": seeded["pot"]})
        await admin.execute(text("DELETE FROM pot_member_permissions WHERE pot_id = :p"), {"p": seeded["pot"]})
        await admin.execute(text("DELETE FROM pots WHERE id = :p"), {"p": seeded["pot"]})
        await admin.commit()

    # Through the REQUEST role, which is what a member deleting their group actually uses.
    async with _as(seeded, "owner") as s:
        await s.execute(text("DELETE FROM groups WHERE id = :g"), {"g": seeded["group"]})
        await s.commit()

    async with seeded["admin_sessionmaker"]() as admin:
        left = (await admin.execute(text("SELECT COUNT(*) FROM shared_audit_log WHERE group_id = :g"), {"g": seeded["group"]})).scalar_one()
        assert left == 0


@pytest.mark.asyncio
async def test_deleting_the_actors_account_leaves_the_entry_and_forgets_the_name(seeded):
    # SET NULL rather than CASCADE, and the same exemption applies: the record of what an account did to
    # money other people share must outlive the account, so the entry stays and only its actor goes.
    async with seeded["admin_sessionmaker"]() as admin:
        await admin.execute(text("DELETE FROM users WHERE id = :u"), {"u": seeded["users"]["owner"]})
        await admin.commit()
        row = (
            await admin.execute(text("SELECT actor_user_id FROM shared_audit_log WHERE id = :i"), {"i": seeded["group_entry"]})
        ).scalar_one_or_none()
    # scalar_one_or_none rather than scalar_one, so a CASCADE reads as None-the-row-is-gone and is told
    # apart from None-the-actor-is-forgotten by the count below.
    assert row is None
    async with seeded["admin_sessionmaker"]() as admin:
        assert (await admin.execute(text("SELECT COUNT(*) FROM shared_audit_log WHERE id = :i"), {"i": seeded["group_entry"]})).scalar_one() == 1


# ---------------------------------------------------------------------------
# The counterparty's delete on a re-agreement
# ---------------------------------------------------------------------------


async def _event_ids(session: AsyncSession, pot_id: int) -> set[int]:
    rows = await session.execute(text("SELECT id FROM pot_ownership_events WHERE pot_id = :p"), {"p": pot_id})
    return {row[0] for row in rows.all()}


@pytest.mark.asyncio
async def test_a_named_counterparty_may_delete_the_reagreement_without_write_access(seeded):
    # The database half of the remedy. The service refuses first, so without this file the policy
    # underneath would refuse the same delete and nothing would say so.
    async with _as(seeded, "counterparty") as s:
        await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["reagreement"]})
        assert seeded["reagreement"] not in await _event_ids(s, seeded["pot"])
        await s.rollback()


@pytest.mark.asyncio
async def test_the_same_seat_may_not_delete_any_other_event_type(seeded):
    """The type narrowing, isolated from the seat narrowing beside it.

    The contribution seeded here is the counterparty's OWN, so their seat matches it — which means the
    `type = 'reagreement'` clause is the only thing refusing the delete. Without it, a co-owner with no
    write access could remove their own contribution and every other owner's share would move.

    A contribution moves the mover's own money and an opening is the division everybody agreed to, so
    neither has a counterparty with a claim to undo it. RLS refuses a DELETE by filtering, so this
    asserts the row SURVIVES rather than that anything raised — and the test above is the positive
    control that keeps "nothing was deleted" from being true of a missing policy.
    """
    async with _as(seeded, "counterparty") as s:
        await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["contribution"]})
        assert seeded["contribution"] in await _event_ids(s, seeded["pot"])
        await s.rollback()


@pytest.mark.asyncio
async def test_a_member_the_reagreement_does_not_name_may_not_delete_it(seeded):
    # The seat narrowing: seeing the pot is not being party to the deal.
    async with _as(seeded, "bystander") as s:
        await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["reagreement"]})
        assert seeded["reagreement"] in await _event_ids(s, seeded["pot"])
        await s.rollback()


@pytest.mark.asyncio
async def test_the_widening_grants_no_insert_and_no_update(seeded):
    """DELETE alone, which is what keeps the remedy from becoming write access.

    The new policy names FOR DELETE, so the existing FOR ALL policy still governs the other commands —
    and its WITH CHECK stays app_can_write_pot. Both halves asserted, because a FOR ALL widening would
    have passed the delete tests above identically.
    """
    async with _as(seeded, "counterparty") as s:
        with pytest.raises(DBAPIError):
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price) "
                    "VALUES (:p, 'reagreement', '2026-04-01', :m, -5, 1)"
                ),
                {"p": seeded["pot"], "m": seeded["seats"]["counterparty"]},
            )
        await s.rollback()
    async with _as(seeded, "counterparty") as s:
        changed = await s.execute(text("UPDATE pot_ownership_events SET units = 0 WHERE id = :i"), {"i": seeded["reagreement"]})
        assert changed.rowcount == 0
        await s.rollback()


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_writers_cannot_hold_the_pots_lock_at_once(seeded):
    """What `SELECT … FOR UPDATE` on the pot actually buys, proven rather than asserted.

    The invariant it protects spans rows that do not exist yet — "is this pot already opened" is
    answered by a SELECT and acted on by an INSERT — so the parent row is the only thing lockable. The
    second writer must WAIT rather than proceed, which is exactly what an unlocked version would not do.

    Driven with a short timeout instead of a race: `NOWAIT` turns "somebody else holds it" into an
    immediate error, so the test is deterministic rather than a sleep.
    """
    first = _as(seeded, "owner")
    second = _as(seeded, "owner")
    try:
        await first.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE"), {"p": seeded["pot"]})
        with pytest.raises(DBAPIError):
            await second.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE NOWAIT"), {"p": seeded["pot"]})
        await second.rollback()
        await first.rollback()
        # And once the first writer is done, the lock is free — so the second is delayed, never refused.
        await second.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE NOWAIT"), {"p": seeded["pot"]})
        await second.rollback()
    finally:
        await first.close()
        await second.close()


@pytest.mark.asyncio
async def test_a_read_only_seat_can_still_take_the_pots_lock(seeded):
    """The property the counterparty remedy depends on.

    A locking read applies the UPDATE policy's USING clause as well as the SELECT one, and
    `pots_scope_write`'s is view-plus-membership rather than write access — so a read-only seat can take
    it, which is what lets the widened delete serialise against the writer who recorded the entry. If
    that policy ever narrowed to app_can_write_pot, this would start failing rather than deadlocking in
    production.
    """
    async with _as(seeded, "counterparty") as s:
        locked = await s.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE"), {"p": seeded["pot"]})
        assert locked.scalar_one() == seeded["pot"]
        await s.rollback()


@pytest.mark.asyncio
async def test_the_group_lock_is_takeable_by_any_member_and_only_by_a_member(seeded):
    # The balance-capped writes lock the group rather than the pot. Both directions, because "it
    # returned nothing" is what a non-member gets from every read of this table anyway.
    async with _as(seeded, "bystander") as s:
        assert (await s.execute(text("SELECT id FROM groups WHERE id = :g FOR UPDATE"), {"g": seeded["group"]})).scalar_one() == seeded["group"]
        await s.rollback()
    async with _as(seeded, "outsider") as s:
        assert (await s.execute(text("SELECT id FROM groups WHERE id = :g FOR UPDATE"), {"g": seeded["group"]})).scalar_one_or_none() is None
        await s.rollback()


@pytest.mark.asyncio
async def test_the_lock_actually_serialises_two_concurrent_writers(seeded):
    """The behaviour the NOWAIT test above cannot show: a waiter that proceeds AFTER the holder commits.

    Two sessions, each taking the lock and appending to a shared list. The second cannot append until
    the first releases, so the order is deterministic — where without the lock both would append
    immediately and the order would be whichever coroutine the loop resumed first.
    """
    order: list[str] = []
    holder_has_lock = asyncio.Event()

    async def holder():
        async with _as(seeded, "owner") as s:
            await s.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE"), {"p": seeded["pot"]})
            holder_has_lock.set()
            # Long enough that the waiter is provably blocked rather than merely slower.
            await asyncio.sleep(0.3)
            order.append("holder")
            await s.rollback()

    async def waiter():
        await holder_has_lock.wait()
        async with _as(seeded, "owner") as s:
            await s.execute(text("SELECT id FROM pots WHERE id = :p FOR UPDATE"), {"p": seeded["pot"]})
            order.append("waiter")
            await s.rollback()

    await asyncio.gather(holder(), waiter())
    assert order == ["holder", "waiter"]
