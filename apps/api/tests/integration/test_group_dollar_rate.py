import asyncio
import os
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import text

# A group's dollar rate and the pot-owner removal guard, run through the real services on the
# RESTRICTED role with a real user context — the shape a request has.
#
# Both need a real Postgres for a reason a mocked session cannot cover. The rate's writes go through the
# group_money_settings and shared_audit_log row policies, which ask whether the WRITER is still a member:
# a member who leaves as the last holdout of a pending change has the change applied by their own
# request, and that only works if it is written before their seat goes inactive. And the removal guard
# reads pot ledgers an admin may not be allowed to see: a pot hidden from the remover still holds the
# removed member's units, which only the privileged session can count.
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.db import set_session_user
from app.domain import (
    GroupBalanceOutstandingError,
    GroupDollarRateAlreadyAgreedError,
    GroupMemberOwnsPotError,
    GroupMemberPotChangePendingError,
    PotSeatDepartedError,
)
from app.models.exchange_rate import DollarRate
from app.models.shared_audit import AuditAction
from app.models.user import User
from app.repositories import group_repository, pot_repository
from app.services import group_money_service, group_service, pot_ownership_service, pot_service

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {
    "admin": "grate_admin@test.local",
    "owner": "grate_owner@test.local",
    "third": "grate_third@test.local",
}
_GROUP = "Group rate integration"


async def _scalar(session: AsyncSession, sql: str, **params):
    return (await session.execute(text(sql), params)).scalar_one()


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM users WHERE email = ANY(:emails)"), {"emails": list(_EMAILS.values())})
    await session.execute(text("DELETE FROM groups WHERE name = :n"), {"n": _GROUP})
    await session.commit()


# One group: an admin, an owner, a third member and a name-only seat. One pot with 'owners' visibility
# that the admin has no row on — so it is hidden from them — split 50/50 between the owner and the
# third member.
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    admin = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)

    async with admin() as s:
        await _cleanup(s)
        users = {
            key: await _scalar(s, "INSERT INTO users (name, email, password_hash) VALUES (:n, :e, 'h') RETURNING id", n=key, e=email)
            for key, email in _EMAILS.items()
        }
        group = await _scalar(s, "INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id", n=_GROUP, u=users["admin"])
        await s.execute(text("INSERT INTO group_money_settings (group_id) VALUES (:g)"), {"g": group})
        seats = {
            key: await _scalar(
                s,
                "INSERT INTO group_members (group_id, user_id, display_name, role) VALUES (:g, :u, :n, :r) RETURNING id",
                g=group,
                u=users[key],
                n=key,
                r="admin" if key == "admin" else "member",
            )
            for key in ("admin", "owner", "third")
        }
        seats["placeholder"] = await _scalar(s, "INSERT INTO group_members (group_id, display_name) VALUES (:g, 'placeholder') RETURNING id", g=group)
        pot = await _scalar(
            s, "INSERT INTO pots (group_id, name, base_currency, visibility) VALUES (:g, 'Hidden', 'USD', 'owners') RETURNING id", g=group
        )
        for key in ("owner", "third"):
            await s.execute(
                text("INSERT INTO pot_member_permissions (pot_id, member_id, can_view, can_write) VALUES (:p, :m, TRUE, TRUE)"),
                {"p": pot, "m": seats[key]},
            )
            await s.execute(
                text(
                    "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price)"
                    " VALUES (:p, 'opening', '2026-01-01', :m, 50, 1)"
                ),
                {"p": pot, "m": seats[key]},
            )
        await s.commit()

    yield {"users": users, "group": group, "seats": seats, "pot": pot, "app": app, "admin": admin}

    async with admin() as s:
        await s.execute(text("DELETE FROM pots WHERE group_id = :g"), {"g": group})
        await _cleanup(s)
    await app_engine.dispose()
    await admin_engine.dispose()


def _user(seeded, key: str) -> User:
    return User(id=seeded["users"][key], name=key, email=_EMAILS[key], password_hash="h", session_epoch=0)


# Runs one service call as `key`, on the restricted role with their context set.
async def _as(seeded, key: str, call):
    async with seeded["app"]() as s:
        set_session_user(s, seeded["users"][key])
        return await call(s, _user(seeded, key))


async def _settings_row(seeded) -> tuple:
    async with seeded["admin"]() as s:
        return (
            await s.execute(
                text("SELECT dollar_rate::text, dollar_rate_proposal::text, dollar_rate_agreed_by FROM group_money_settings WHERE group_id = :g"),
                {"g": seeded["group"]},
            )
        ).one()


async def _is_active(seeded, key: str) -> bool:
    async with seeded["admin"]() as s:
        return await _scalar(s, "SELECT is_active FROM group_members WHERE id = :m", m=seeded["seats"][key])


# Moves the owner's whole share to the third member — the effect a buy-out has on the ledger.
async def _buy_out_owner(seeded) -> None:
    async with seeded["admin"]() as s:
        await s.execute(
            text(
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, counterparty_member_id, units, unit_price, confirmed_at)"
                " VALUES (:p, 'reagreement', '2026-02-01', :m, :c, -50, 1, NOW())"
            ),
            {"p": seeded["pot"], "m": seeded["seats"]["owner"], "c": seeded["seats"]["third"]},
        )
        await s.commit()


class TestTheMembersAgree:
    @pytest.mark.asyncio
    async def test_a_change_waits_for_every_active_member_and_then_applies(self, seeded):
        group = seeded["group"]
        await _as(seeded, "admin", lambda s, u: group_money_service.propose_dollar_rate(s, group, u, dollar_rate=DollarRate.blue))
        assert await _settings_row(seeded) == ("mep", "blue", [seeded["seats"]["admin"]])

        # The placeholder is never waited for; the owner and the third member are.
        read = await _as(seeded, "owner", lambda s, u: group_money_service.get_settings(s, group, u))
        assert sorted(read.dollar_rate_proposal.waiting_on) == ["owner", "third"]
        assert read.dollar_rate_proposal.can_agree is True

        await _as(seeded, "owner", lambda s, u: group_money_service.agree_dollar_rate(s, group, u))
        with pytest.raises(GroupDollarRateAlreadyAgreedError):
            await _as(seeded, "owner", lambda s, u: group_money_service.agree_dollar_rate(s, group, u))
        assert (await _settings_row(seeded))[0] == "mep"

        await _as(seeded, "third", lambda s, u: group_money_service.agree_dollar_rate(s, group, u))
        assert await _settings_row(seeded) == ("blue", None, [])

        async with seeded["admin"]() as s:
            steps = (
                await s.execute(
                    text(
                        "SELECT action::text, payload->>'variant' FROM shared_audit_log"
                        " WHERE group_id = :g AND entity_type = 'group_money_settings' ORDER BY id"
                    ),
                    {"g": group},
                )
            ).all()
        assert steps == [("updated", "dollar_rate_proposed"), ("confirmed", None), ("confirmed", None), ("updated", "dollar_rate")]

    @pytest.mark.asyncio
    async def test_the_last_holdout_leaving_applies_the_change_and_the_leave_still_succeeds(self, seeded):
        # The leaver's own request writes the settings row and an audit entry, both behind policies that
        # ask whether the writer is a member — so this only passes if it happens before the seat goes.
        group = seeded["group"]
        await _buy_out_owner(seeded)
        await _as(seeded, "admin", lambda s, u: group_money_service.propose_dollar_rate(s, group, u, dollar_rate=DollarRate.oficial))
        await _as(seeded, "third", lambda s, u: group_money_service.agree_dollar_rate(s, group, u))
        assert (await _settings_row(seeded))[1] == "oficial"

        async with seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(s, seeded["users"]["owner"])
            await group_service.remove_member(s, admin_session, group, seeded["seats"]["owner"], _user(seeded, "owner"))

        assert await _is_active(seeded, "owner") is False
        assert await _settings_row(seeded) == ("oficial", None, [])


class TestAPotOwnerCannotLeaveTheirShareBehind:
    @pytest.mark.asyncio
    async def test_an_admin_cannot_remove_an_owner_of_a_pot_hidden_from_them(self, seeded):
        group, seats = seeded["group"], seeded["seats"]
        async with seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(s, seeded["users"]["admin"])
            # The pot really is hidden from the remover: the check cannot be leaning on their view of it.
            assert (await s.execute(text("SELECT count(*) FROM pots WHERE id = :p"), {"p": seeded["pot"]})).scalar_one() == 0
            with pytest.raises(GroupMemberOwnsPotError):
                await group_service.remove_member(s, admin_session, group, seats["owner"], _user(seeded, "admin"))
        assert await _is_active(seeded, "owner") is True

    @pytest.mark.asyncio
    async def test_an_owner_cannot_leave_either(self, seeded):
        async with seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(s, seeded["users"]["owner"])
            with pytest.raises(GroupMemberOwnsPotError):
                await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "owner"))
        assert await _is_active(seeded, "owner") is True

    @pytest.mark.asyncio
    async def test_once_the_share_is_bought_out_the_removal_goes_through(self, seeded):
        await _buy_out_owner(seeded)
        async with seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(s, seeded["users"]["admin"])
            await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "admin"))
        assert await _is_active(seeded, "owner") is False


class TestARemovalAndALedgerWriteCannotInterleave:
    # The window between counting a seat's units and deactivating it. A removal holds the SEAT's lock
    # (exclusively) while it counts; a ledger write that hands the seat units takes the same lock (shared)
    # after its pot's. So whichever comes second waits. Proved by holding one side open and watching the
    # other time out on the lock rather than slip through.

    @pytest.mark.asyncio
    async def test_a_buy_in_waits_for_a_removal_holding_the_seat(self, seeded):
        async with seeded["app"]() as removal, seeded["app"]() as writer:
            set_session_user(removal, seeded["users"]["admin"])
            set_session_user(writer, seeded["users"]["third"])
            await group_repository.lock_members(removal, [seeded["seats"]["owner"]])
            await writer.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await pot_ownership_service.record_reagreement(
                    writer,
                    seeded["pot"],
                    _user(seeded, "third"),
                    date=date(2026, 3, 1),
                    from_member_id=seeded["seats"]["third"],
                    to_member_id=seeded["seats"]["owner"],
                    percentage=Decimal("10"),
                )
            await writer.rollback()
            await removal.rollback()

    @pytest.mark.asyncio
    async def test_a_removal_waits_for_a_ledger_write_in_flight(self, seeded):
        await _buy_out_owner(seeded)
        async with seeded["app"]() as writer, seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(writer, seeded["users"]["third"])
            set_session_user(s, seeded["users"]["admin"])
            # A write handing the owner units, between its locks and its commit.
            await pot_repository.lock(writer, seeded["pot"])
            await group_repository.lock_members(writer, [seeded["seats"]["owner"]], shared=True)
            await s.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "admin"))
            await s.rollback()
            await writer.rollback()
        assert await _is_active(seeded, "owner") is True

    @pytest.mark.asyncio
    async def test_a_removal_racing_a_buy_in_counts_the_units_it_waited_for(self, seeded):
        # The race itself, end to end: the owner's share has gone, a buy-in handing them units is in
        # flight, and an admin removes them meanwhile. The removal must see those units and refuse —
        # not count an empty ledger, then wait out the write and deactivate a seat that owns part of
        # the pot.
        await _buy_out_owner(seeded)

        # A ledger write handing the owner units, following the protocol every ledger write does (the
        # pot's lock, then the receiving seat's, shared), held open between its insert and its commit so
        # the removal arrives in between.
        async def buy_in():
            async with seeded["app"]() as writer:
                set_session_user(writer, seeded["users"]["third"])
                await pot_repository.lock(writer, seeded["pot"])
                await group_repository.lock_members(writer, [seeded["seats"]["owner"]], shared=True)
                await writer.execute(
                    text(
                        "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, counterparty_member_id, units, unit_price)"
                        " VALUES (:p, 'reagreement', '2026-03-01', :m, :c, -10, 1)"
                    ),
                    {"p": seeded["pot"], "m": seeded["seats"]["third"], "c": seeded["seats"]["owner"]},
                )
                await asyncio.sleep(0.6)
                await writer.commit()

        async def remove():
            await asyncio.sleep(0.2)
            async with seeded["app"]() as s, seeded["admin"]() as admin_session:
                set_session_user(s, seeded["users"]["admin"])
                await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "admin"))

        results = await asyncio.wait_for(asyncio.gather(buy_in(), remove(), return_exceptions=True), timeout=15)
        assert isinstance(results[1], GroupMemberOwnsPotError), results
        assert await _is_active(seeded, "owner") is True

    @pytest.mark.asyncio
    async def test_editing_a_pot_and_a_ledger_write_do_not_deadlock(self, seeded):
        # The independent review's reproduction: an edit of the pot's row whose audit entry references
        # the group, racing a ledger write that holds the pot. Both must finish, in some order.
        async def edit():
            async with seeded["app"]() as editor:
                set_session_user(editor, seeded["users"]["owner"])
                pot = await pot_repository.get_by_id(editor, seeded["pot"])
                pot.name = "renamed"
                await pot_repository.save(editor, pot)
                await editor.flush()
                await asyncio.sleep(0.3)
                await pot_service._audit(editor, pot, _user(seeded, "owner"), AuditAction.updated)
                await editor.commit()

        async def write():
            await asyncio.sleep(0.1)
            async with seeded["app"]() as writer:
                set_session_user(writer, seeded["users"]["third"])
                await pot_repository.lock(writer, seeded["pot"])
                await pot_service._audit(writer, await pot_repository.get_by_id(writer, seeded["pot"]), _user(seeded, "third"), AuditAction.updated)
                await writer.commit()

        async with seeded["app"]() as holder:
            # Somebody holding the group the way a removal or a settle-up does, released mid-race.
            set_session_user(holder, seeded["users"]["admin"])
            await group_repository.lock(holder, seeded["group"])
            results = await asyncio.wait_for(asyncio.gather(edit(), write(), _release(holder, 0.5), return_exceptions=True), timeout=10)
        assert [type(r).__name__ for r in results if isinstance(r, Exception)] == []
        async with seeded["admin"]() as s:
            assert await _scalar(s, "SELECT name FROM pots WHERE id = :p", p=seeded["pot"]) == "renamed"


async def _release(session: AsyncSession, after: float) -> None:
    await asyncio.sleep(after)
    await session.commit()


class TestAShareCannotComeBackToASeatThatHasGone:
    @pytest.mark.asyncio
    async def test_leaving_is_refused_while_a_buy_out_naming_the_seat_waits_for_confirmation(self, seeded):
        await _sell_owner_share_unconfirmed(seeded)
        async with seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(s, seeded["users"]["owner"])
            with pytest.raises(GroupMemberPotChangePendingError):
                await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "owner"))
        assert await _is_active(seeded, "owner") is True

    @pytest.mark.asyncio
    async def test_deleting_a_take_out_of_a_departed_seat_is_refused(self, seeded):
        # The independent review's path, through a take-out, which has no confirmation to wait for: the
        # owner's whole share leaves, they leave the group, and somebody deletes the entry.
        async with seeded["admin"]() as s:
            event = await _scalar(
                s,
                "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, units, unit_price, amount)"
                " VALUES (:p, 'withdrawal', '2026-02-01', :m, -50, 1, 50) RETURNING id",
                p=seeded["pot"],
                m=seeded["seats"]["owner"],
            )
            await s.commit()
        async with seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(s, seeded["users"]["owner"])
            await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "owner"))
        with pytest.raises(PotSeatDepartedError):
            await _as(seeded, "third", lambda s, u: pot_ownership_service.delete_event(s, seeded["pot"], event, u))
        async with seeded["admin"]() as s:
            assert await _scalar(s, "SELECT count(*) FROM pot_ownership_events WHERE id = :e", e=event) == 1

    @pytest.mark.asyncio
    async def test_deleting_a_buy_out_after_its_seller_deleted_their_account_is_refused(self, seeded):
        # The account-deletion half: the seat stays active but loses its account.
        event = await _sell_owner_share_unconfirmed(seeded, confirmed=True)
        async with seeded["admin"]() as s:
            await s.execute(text("UPDATE pot_ownership_events SET confirmed_at = NULL WHERE id = :e"), {"e": event})
            await s.execute(text("UPDATE group_members SET user_id = NULL, joined_at = NOW() WHERE id = :m"), {"m": seeded["seats"]["owner"]})
            await s.commit()
        with pytest.raises(PotSeatDepartedError):
            await _as(seeded, "third", lambda s, u: pot_ownership_service.delete_event(s, seeded["pot"], event, u))


# The owner sells their whole share to the third member, as a buy-out not yet confirmed.
async def _sell_owner_share_unconfirmed(seeded, *, confirmed: bool = False) -> int:
    async with seeded["admin"]() as s:
        event = await _scalar(
            s,
            "INSERT INTO pot_ownership_events (pot_id, type, date, member_id, counterparty_member_id, units, unit_price, confirmed_at)"
            " VALUES (:p, 'reagreement', '2026-02-01', :m, :c, -50, 1, " + ("NOW()" if confirmed else "NULL") + ") RETURNING id",
            p=seeded["pot"],
            m=seeded["seats"]["owner"],
            c=seeded["seats"]["third"],
        )
        await s.commit()
    return event


class TestTheLockOrderHoldsAgainstEveryOtherWriter:
    # The independent review's round-two reproductions: each pairs a removal with a path that takes the
    # locks around it in some other combination, and each must finish rather than deadlock — group, pot,
    # seat, in that order, with the group's lock letting rows that merely name the group through.

    @staticmethod
    async def _removal_racing_a_group_holder(seeded, write_sql: str) -> list:
        # Somebody holding the group the way a settle-up or a rate proposal does, who then writes a row
        # naming the leaving seat, while that seat's own removal runs.
        await _buy_out_owner(seeded)
        outcomes: list = []
        async with seeded["app"]() as holder:
            set_session_user(holder, seeded["users"]["admin"])
            await group_repository.lock(holder, seeded["group"])

            async def removal():
                async with seeded["app"]() as s, seeded["admin"]() as admin_session:
                    set_session_user(s, seeded["users"]["owner"])
                    await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "owner"))

            task = asyncio.create_task(removal())
            await asyncio.sleep(0.5)
            params = {"g": seeded["group"], "m": seeded["seats"]["owner"], "a": seeded["seats"]["admin"], "u": seeded["users"]["admin"]}
            await holder.execute(text(write_sql), params)
            await holder.commit()
            try:
                await asyncio.wait_for(task, timeout=10)
                outcomes.append(None)
            except Exception as error:  # noqa: BLE001 — the outcome IS the assertion
                outcomes.append(error)
        return outcomes

    @pytest.mark.asyncio
    async def test_a_settlement_naming_the_seat_finishes_and_the_removal_then_sees_its_balance(self, seeded):
        [outcome] = await self._removal_racing_a_group_holder(
            seeded,
            "INSERT INTO group_settlements (group_id, from_member_id, to_member_id, date, amount, currency, created_by)"
            " VALUES (:g, :m, :a, '2026-11-01', 1, 'USD', :u)",
        )
        # The settlement got there first and opened a balance, so the removal is refused for it.
        assert isinstance(outcome, GroupBalanceOutstandingError), outcome
        assert await _is_active(seeded, "owner") is True

    @pytest.mark.asyncio
    async def test_a_rate_proposal_naming_the_seat_finishes_and_so_does_the_removal(self, seeded):
        [outcome] = await self._removal_racing_a_group_holder(
            seeded,
            "UPDATE group_money_settings SET dollar_rate_proposal = 'blue', dollar_rate_proposed_by = :m,"
            " dollar_rate_agreed_by = ARRAY[:m]::bigint[] WHERE group_id = :g",
        )
        assert outcome is None
        assert await _is_active(seeded, "owner") is False

    @pytest.mark.asyncio
    async def test_a_ledger_write_holding_the_seat_still_writes_its_audit_row_while_a_removal_waits(self, seeded):
        await _buy_out_owner(seeded)
        async with seeded["app"]() as writer:
            set_session_user(writer, seeded["users"]["third"])
            pot = await pot_repository.get_by_id(writer, seeded["pot"])
            await pot_repository.lock(writer, pot.id)
            await group_repository.lock_members(writer, [seeded["seats"]["owner"]], shared=True)

            async def removal():
                async with seeded["app"]() as s, seeded["admin"]() as admin_session:
                    set_session_user(s, seeded["users"]["owner"])
                    await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "owner"))

            task = asyncio.create_task(removal())
            await asyncio.sleep(0.5)
            # The removal now holds the group and waits for the seat; the audit row names the group.
            await pot_service._audit(writer, pot, _user(seeded, "third"), AuditAction.updated)
            await writer.commit()
            await asyncio.wait_for(task, timeout=10)
        assert await _is_active(seeded, "owner") is False

    @pytest.mark.asyncio
    async def test_editing_a_pot_through_the_service_beside_a_ledger_write(self, seeded):
        # Visible to the admin who edits it.
        async with seeded["admin"]() as s:
            await s.execute(text("UPDATE pots SET visibility = 'members' WHERE id = :p"), {"p": seeded["pot"]})
            await s.commit()

        async def edit():
            await _as(seeded, "admin", lambda s, u: pot_service.update_pot(s, seeded["pot"], u, name="renamed"))

        async def ledger():
            async with seeded["app"]() as writer:
                set_session_user(writer, seeded["users"]["owner"])
                await pot_repository.lock(writer, seeded["pot"])
                await group_repository.lock_members(writer, [seeded["seats"]["owner"]], shared=True)
                await asyncio.sleep(0.4)
                await pot_service._audit(writer, await pot_repository.get_by_id(writer, seeded["pot"]), _user(seeded, "owner"), AuditAction.updated)
                await writer.commit()

        results = await asyncio.wait_for(asyncio.gather(ledger(), edit(), return_exceptions=True), timeout=10)
        assert [r for r in results if isinstance(r, Exception)] == []
