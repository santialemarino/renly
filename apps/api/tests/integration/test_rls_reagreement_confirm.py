import os
from datetime import date, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The re-agreement confirmation's database half: who may give it, and what it locks.
#
# Every rule here exists twice on purpose — `pot_ownership_service._confirming_member_id` in Python and
# `pot_ownership_events_confirm_update` in SQL — and the failure that matters is the two DISAGREEING,
# which no unit test can see because a mocked session returns whatever it was told. Three things live
# ONLY in the database and nothing above them can be substituted for any of them:
#
#   * The affected-seat expression. It is not "either named seat": it is the giver unless the giver
#     recorded the change, in which case the receiver. What that buys over a set of two seats is the one
#     case a set gets wrong — a third party with write access recording a change between two other
#     members, where a set would let the member who GAINED units lock the member who lost them out of
#     their remedy.
#
#   * The column GRANT. RLS filters rows and never columns, so a policy cannot say "you may write
#     confirmed_at and nothing else". `REVOKE UPDATE` plus `GRANT UPDATE (confirmed_at)` is what says
#     it, and a permission error rather than a filtered no-op is the visible difference.
#
#   * The LOCK, which is what makes confirming more than a label. Both DELETE policies carry
#     `confirmed_at IS NULL`, so a confirmed entry is undeletable by the pot's own writer as well as by
#     the two seats it names — and the service refusing first is exactly why nothing else would notice
#     if the database stopped agreeing.
#
# Uses the same env vars as test_rls_isolation.py so the whole RLS set runs together.
from app.db import set_session_user

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_GROUP_NAME = "confirm_rls_group"
_EMAILS = {
    # Created the pot, so the only seat with can_write — which is the whole configuration this unit is
    # about: write access is granted to a pot's creator and to nobody else.
    "writer": "confirm_rls_writer@test.local",
    # Gives units away in every seeded re-agreement. Read-only on the pot.
    "giver": "confirm_rls_giver@test.local",
    # Receives them. Read-only on the pot.
    "receiver": "confirm_rls_receiver@test.local",
    # In the group, sees the pot, named on nothing.
    "bystander": "confirm_rls_bystander@test.local",
    # In the group and explicitly denied view of the pot — and the GIVER of one seeded re-agreement, so
    # a seat match alone is not what refuses them.
    "denied": "confirm_rls_denied@test.local",
    # In no group at all.
    "outsider": "confirm_rls_outsider@test.local",
}


# Seeds one pot with a baseline, a contribution, and five re-agreements that differ ONLY in who
# recorded them (and one in whether it is already confirmed) — because that column is the whole input
# to the rule under test.
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
                {"g": _GROUP_NAME, "u": users["writer"]},
            )
        ).scalar_one()
        seats = {}
        for key in ("writer", "giver", "receiver", "bystander", "denied"):
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
            {"p": pot, "m": seats["writer"]},
        )
        for key in ("giver", "receiver"):
            await s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, FALSE)"),
                {"p": pot, "m": seats[key]},
            )
        # can_view FALSE. The bystander gets no row at all, so they fall back to the pot's 'members'
        # default and can see it.
        await s.execute(
            text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, FALSE, FALSE)"),
            {"p": pot, "m": seats["denied"]},
        )
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price, created_by) "
                "VALUES (:p, 'opening', '2026-01-01', :m, 100, 1, :u)"
            ),
            {"p": pot, "m": seats["giver"], "u": users["writer"]},
        )

        async def _reagreement(*, recorded_by, giver_seat=None, confirmed=False, day="02") -> int:
            return (
                await s.execute(
                    text(
                        "INSERT INTO pot_ownership_events "
                        "(pot_id, type, date, member_id, counterparty_member_id, units, unit_price, created_by, confirmed_at) "
                        "VALUES (:p, 'reagreement', :d, :from, :to, -5, 1, :by, :at) RETURNING id"
                    ),
                    {
                        "p": pot,
                        "d": date(2026, int(day), 1),
                        "from": giver_seat if giver_seat is not None else seats["giver"],
                        "to": seats["receiver"],
                        "by": recorded_by,
                        "at": datetime(2026, 9, 1, 12, 0) if confirmed else None,
                    },
                )
            ).scalar_one()

        events = {
            # The case the single expression exists for: neither named seat recorded it.
            "by_writer": await _reagreement(recorded_by=users["writer"], day="02"),
            "by_giver": await _reagreement(recorded_by=users["giver"], day="03"),
            "by_receiver": await _reagreement(recorded_by=users["receiver"], day="04"),
            # created_by is SET NULL when an account is deleted, so this is a real state.
            "orphaned": await _reagreement(recorded_by=None, day="05"),
            "confirmed": await _reagreement(recorded_by=users["writer"], confirmed=True, day="06"),
            # The denied member is the GIVER here, so their seat matches and only the view clause (or
            # the read policy above it) can refuse them.
            "denied_is_giver": await _reagreement(recorded_by=users["writer"], giver_seat=seats["denied"], day="07"),
        }
        # The giver's OWN contribution. Their seat matches it, so the `type = 'reagreement'` clause is
        # the only thing that can refuse a confirmation on it.
        events["contribution"] = (
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, base_amount, units, unit_price, created_by) "
                    "VALUES (:p, 'contribution', '2026-08-01', :m, 10, 10, 1, :u) RETURNING id"
                ),
                {"p": pot, "m": seats["giver"], "u": users["giver"]},
            )
        ).scalar_one()
        await s.commit()

    yield {
        "users": users,
        "seats": seats,
        "group": group,
        "pot": pot,
        "events": events,
        "sessionmaker": app_sessionmaker,
        "admin": admin_sessionmaker,
    }

    async with admin_sessionmaker() as s:
        await _cleanup(s)
        await s.commit()
    await app_engine.dispose()
    await admin_engine.dispose()


async def _cleanup(s: AsyncSession) -> None:
    pots = f"SELECT id FROM pots WHERE group_id IN (SELECT id FROM groups WHERE name = '{_GROUP_NAME}')"
    await s.execute(text(f"DELETE FROM pot_ownership_events WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM pot_member_permissions WHERE pot_id IN ({pots})"))
    await s.execute(text(f"DELETE FROM pots WHERE id IN ({pots})"))
    await s.execute(text("DELETE FROM groups WHERE name = :g"), {"g": _GROUP_NAME})
    await s.execute(text("DELETE FROM users WHERE email = ANY(:e)"), {"e": list(_EMAILS.values())})


# Opens a restricted-role session with the per-request user context set to one seeded user. The
# after_begin listener registered by importing app.db is what applies it as a GUC, so these tests run
# the real isolation mechanism rather than a reimplementation of it.
def _as(seeded, key: str) -> AsyncSession:
    session = seeded["sessionmaker"]()
    set_session_user(session, seeded["users"][key])
    return session


# How many rows the confirmation reached. RLS refuses an UPDATE by FILTERING, so 0 is the refusal and
# there is nothing to catch — which is exactly why every negative case below asserts the count.
async def _confirm(session: AsyncSession, event_id: int, *, at: datetime | None = datetime(2026, 9, 8, 12, 0)) -> int:
    result = await session.execute(text("UPDATE pot_ownership_events SET confirmed_at = :at WHERE id = :i"), {"at": at, "i": event_id})
    return int(result.rowcount or 0)


async def _event_ids(session: AsyncSession, pot_id: int) -> set[int]:
    rows = await session.execute(text("SELECT id FROM pot_ownership_events WHERE pot_id = :p"), {"p": pot_id})
    return {row[0] for row in rows.all()}


# ---------------------------------------------------------------------------
# Who the affected seat is
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_third_party_recording_it_leaves_the_confirm_with_the_GIVER(seeded):
    """The case the whole expression exists for, and the one a set of both named seats gets wrong.

    The pot's writer recorded a change between two other members. The seat with something taken is the
    giver, so theirs is the agreement worth having — and if the RECEIVER could confirm instead, they
    would lock the giver out of the remedy PR 10 shipped, which is the exact harm this is meant to stop.
    """
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["by_writer"]) == 1
        await s.rollback()
    async with _as(seeded, "receiver") as s:
        assert await _confirm(s, seeded["events"]["by_writer"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_the_giver_recording_it_hands_the_confirm_to_the_RECEIVER(seeded):
    # Nobody vouches for their own act, which is the whole point of a confirmation.
    async with _as(seeded, "receiver") as s:
        assert await _confirm(s, seeded["events"]["by_giver"]) == 1
        await s.rollback()
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["by_giver"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_the_receiver_recording_it_leaves_the_confirm_with_the_giver(seeded):
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["by_receiver"]) == 1
        await s.rollback()
    async with _as(seeded, "receiver") as s:
        assert await _confirm(s, seeded["events"]["by_receiver"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_a_recorder_whose_account_is_gone_leaves_the_confirm_with_the_giver(seeded):
    """`giver.user_id = created_by` is a plain equality, not IS NOT DISTINCT FROM, and this is why.

    created_by is SET NULL when an account is deleted, so a NULL there is a real state rather than a
    hypothetical. The comparison then yields NULL, the CASE falls to its ELSE, and the answer stays on
    the seat with something taken — the safe direction, and the one the Python side reproduces.
    """
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["orphaned"]) == 1
        await s.rollback()
    async with _as(seeded, "receiver") as s:
        assert await _confirm(s, seeded["events"]["orphaned"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_the_pots_WRITER_cannot_confirm_an_entry_they_are_not_the_affected_seat_of(seeded):
    """The sharpest statement of the decision: write access is NOT the trust boundary.

    This seat may insert and delete every other entry in the ledger, and it recorded this one. If write
    access carried the confirmation, the person who moved the units would also be the person who
    vouches for the move — which is the default configuration a divided pot ships in, not an edge case.
    """
    async with _as(seeded, "writer") as s:
        assert await _confirm(s, seeded["events"]["by_writer"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_a_member_named_on_neither_side_cannot_confirm(seeded):
    # Seeing the pot is not being party to the deal — the same narrowing the delete remedy carries.
    async with _as(seeded, "bystander") as s:
        assert await _confirm(s, seeded["events"]["by_writer"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_a_member_denied_the_pot_cannot_confirm_the_change_to_their_OWN_share(seeded):
    """Fail-closed, and asserted on a row whose seat DOES match so the seat check is not what refuses.

    A member with can_view false is refused both by the read policy (so the WHERE finds nothing) and by
    the confirm policy's own app_can_view_pot clause; this proves the outcome rather than which of the
    two got there first. It is the same posture the notification layer takes — a member who cannot view
    a pot is not in its audience either.
    """
    async with _as(seeded, "denied") as s:
        assert await _confirm(s, seeded["events"]["denied_is_giver"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_a_deactivated_seat_cannot_confirm(seeded):
    # is_active is part of the predicate, so removing a member revokes this with everything else.
    async with seeded["admin"]() as admin:
        await admin.execute(text("UPDATE group_members SET is_active = FALSE WHERE id = :m"), {"m": seeded["seats"]["giver"]})
        await admin.commit()
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["by_writer"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_a_context_less_session_confirms_nothing(seeded):
    # app_current_user_id() is NULL with no GUC set, so the join matches nothing and the whole predicate
    # fails closed. Every policy in this schema has this property; it is asserted per table.
    session = seeded["sessionmaker"]()
    async with session as s:
        assert await _confirm(s, seeded["events"]["by_writer"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_no_other_event_type_can_be_confirmed(seeded):
    """The type narrowing, isolated from the seat narrowing beside it.

    The contribution seeded here is the giver's OWN, so their seat matches — which means
    `type = 'reagreement'` is the only clause that can refuse it. A CHECK constraint refuses the row
    underneath as well, and both directions matter: one keeps the column meaningful, the other keeps
    the policy honest.
    """
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["contribution"]) == 0
        await s.rollback()


@pytest.mark.asyncio
async def test_the_CHECK_refuses_a_confirmation_on_another_event_type_even_as_the_owner(seeded):
    # The constraint rather than the policy, so it holds for the privileged session too — which is what
    # keeps the column's meaning from depending on who is writing.
    async with seeded["admin"]() as admin:
        with pytest.raises(DBAPIError):
            await admin.execute(text("UPDATE pot_ownership_events SET confirmed_at = NOW() WHERE id = :i"), {"i": seeded["events"]["contribution"]})
        await admin.rollback()


@pytest.mark.asyncio
async def test_the_unconfirm_is_the_same_policy_running_backwards(seeded):
    # Setting the column back to NULL is the same UPDATE, so the same seat governs both directions —
    # which is what makes withdrawing a confirmation the affected seat's alone.
    async with _as(seeded, "giver") as s:
        assert await _confirm(s, seeded["events"]["confirmed"], at=None) == 1
        await s.rollback()
    async with _as(seeded, "writer") as s:
        assert await _confirm(s, seeded["events"]["confirmed"], at=None) == 0
        await s.rollback()


# ---------------------------------------------------------------------------
# The column grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_the_affected_seat_cannot_rewrite_the_units_it_is_agreeing_to(seeded):
    """RLS filters ROWS and never columns, so the policy above cannot say this — the grant does.

    Without `REVOKE UPDATE` plus `GRANT UPDATE (confirmed_at)`, the seat entitled to confirm a
    re-agreement could rewrite its `units` on the way, which would make every derived balance a claim
    about the present rather than a replay of what happened. A permission ERROR rather than a filtered
    no-op is also the point: RLS refuses by returning "nothing changed", which looks identical to a row
    that did not match.
    """
    async with _as(seeded, "giver") as s:
        with pytest.raises(DBAPIError):
            await s.execute(text("UPDATE pot_ownership_events SET units = 0 WHERE id = :i"), {"i": seeded["events"]["by_writer"]})
        await s.rollback()


@pytest.mark.asyncio
async def test_not_even_the_pots_writer_may_update_any_other_column(seeded):
    # The grant is on the ROLE, so it holds for every seat: the ledger is insert-and-delete, and the
    # confirmation is the one column anything ever changes.
    async with _as(seeded, "writer") as s:
        for column, value in (("units", "0"), ("date", "'2020-01-01'"), ("member_id", "0")):
            with pytest.raises(DBAPIError):
                await s.execute(text(f"UPDATE pot_ownership_events SET {column} = {value} WHERE id = :i"), {"i": seeded["events"]["by_writer"]})
            await s.rollback()


@pytest.mark.asyncio
async def test_the_writer_keeps_insert_and_delete(seeded):
    """The positive control for both tests above.

    Splitting the old FOR ALL policy per command could have taken INSERT or DELETE with it, and every
    refusal test here would have passed identically brighter. This is what says the split kept what it
    was meant to keep.
    """
    async with _as(seeded, "writer") as s:
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price, created_by) "
                "VALUES (:p, 'withdrawal', '2026-09-01', :m, -1, 1, :u)"
            ),
            {"p": seeded["pot"], "m": seeded["seats"]["giver"], "u": seeded["users"]["writer"]},
        )
        await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["events"]["by_writer"]})
        assert seeded["events"]["by_writer"] not in await _event_ids(s, seeded["pot"])
        await s.rollback()


# ---------------------------------------------------------------------------
# The lock
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_confirmed_reagreement_cannot_be_deleted_by_the_pots_writer(seeded):
    # `confirmed_at IS NULL` on pot_ownership_events_scope_delete. Without it the seat that agreed could
    # have the entry removed out from under them by the very person whose act they vouched for.
    async with _as(seeded, "writer") as s:
        await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["events"]["confirmed"]})
        assert seeded["events"]["confirmed"] in await _event_ids(s, seeded["pot"])
        await s.rollback()


@pytest.mark.asyncio
async def test_a_confirmed_reagreement_cannot_be_deleted_by_either_named_seat(seeded):
    # `confirmed_at IS NULL` on pot_ownership_events_counterparty_delete. The remedy is what a seat has
    # BEFORE they agree, and agreeing is what gives it up.
    for key in ("giver", "receiver"):
        async with _as(seeded, key) as s:
            await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["events"]["confirmed"]})
            assert seeded["events"]["confirmed"] in await _event_ids(s, seeded["pot"]), key
            await s.rollback()


@pytest.mark.asyncio
async def test_the_same_seats_may_delete_the_same_entry_once_it_is_unconfirmed(seeded):
    """The positive control for the two tests above, and it needs to be here.

    RLS refuses a DELETE by filtering, so "the row survived" is also true of a policy that was dropped
    altogether, of a seat that never matched, and of a fixture whose id was wrong. The only thing that
    separates a working lock from a broken policy is the same seats succeeding the moment the
    confirmation is gone.
    """
    async with seeded["admin"]() as admin:
        await admin.execute(text("UPDATE pot_ownership_events SET confirmed_at = NULL WHERE id = :i"), {"i": seeded["events"]["confirmed"]})
        await admin.commit()
    for key in ("writer", "giver", "receiver"):
        async with _as(seeded, key) as s:
            await s.execute(text("DELETE FROM pot_ownership_events WHERE id = :i"), {"i": seeded["events"]["confirmed"]})
            assert seeded["events"]["confirmed"] not in await _event_ids(s, seeded["pot"]), key
            await s.rollback()
