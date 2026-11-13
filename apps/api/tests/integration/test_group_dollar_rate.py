import os

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
from app.domain import GroupDollarRateAlreadyAgreedError, GroupMemberOwnsPotError
from app.models.exchange_rate import DollarRate
from app.models.user import User
from app.repositories import group_repository, pot_repository
from app.services import group_money_service, group_service

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
    # The window between counting a seat's units and deactivating it. Every ledger write takes its
    # group's lock before its pot's (pot_repository.lock), and a removal holds the group's lock while it
    # counts — so whichever comes second waits. Proved by holding one side open and watching the other
    # time out on the lock rather than slip through.

    @pytest.mark.asyncio
    async def test_a_ledger_write_waits_for_a_removal_holding_the_group(self, seeded):
        async with seeded["app"]() as removal, seeded["app"]() as writer:
            set_session_user(removal, seeded["users"]["admin"])
            set_session_user(writer, seeded["users"]["owner"])
            await group_repository.lock(removal, seeded["group"])
            await writer.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await pot_repository.lock(writer, seeded["pot"])
            await writer.rollback()
            await removal.rollback()

    @pytest.mark.asyncio
    async def test_a_removal_waits_for_a_ledger_write_in_flight(self, seeded):
        await _buy_out_owner(seeded)
        async with seeded["app"]() as writer, seeded["app"]() as s, seeded["admin"]() as admin_session:
            set_session_user(writer, seeded["users"]["third"])
            set_session_user(s, seeded["users"]["admin"])
            # A contribution for the owner, between its lock and its commit.
            await pot_repository.lock(writer, seeded["pot"])
            await s.execute(text("SET LOCAL lock_timeout = '300ms'"))
            with pytest.raises(DBAPIError, match="lock timeout"):
                await group_service.remove_member(s, admin_session, seeded["group"], seeded["seats"]["owner"], _user(seeded, "admin"))
            await s.rollback()
            await writer.rollback()
        assert await _is_active(seeded, "owner") is True
