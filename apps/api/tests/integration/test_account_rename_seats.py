import asyncio
import os

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# Renaming the account into the user's group seats, run through the real service on the RESTRICTED role
# with a real user context — the shape a request has.
#
# Three things only a real Postgres shows. Which seats the query returns: the user's own and active ones,
# never another account's seat or a placeholder that happens to carry the same name. The locks: a rename
# waits for an admin renaming the same seat, or for another rename of the same account, and then decides
# from what they committed. And the transaction: a failure part way leaves the account and every seat as
# they were. The rule that picks seats by name, and the endpoint shapes, are pinned in
# tests/unit/test_profile_update.py.
from app.db import set_session_user
from app.models.user import User
from app.services import shared_audit_service, user_account_service

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_EMAILS = {
    # The account being renamed, called "Santi".
    "me": "rename_seats_me@test.local",
    # Another account that is ALSO called "Santi", and admin of the shared groups.
    "other": "rename_seats_other@test.local",
}
_GROUPS = {
    # Each name is its own group, so a test can name the one it means.
    "mine": "Rename seats — mine",
    "shared": "Rename seats — shared",
    "nickname": "Rename seats — nickname",
    "former": "Rename seats — former",
}


async def _scalar(session: AsyncSession, sql: str, **params):
    return (await session.execute(text(sql), params)).scalar_one()


async def _cleanup(session: AsyncSession) -> None:
    await session.execute(text("DELETE FROM groups WHERE name = ANY(:names)"), {"names": list(_GROUPS.values())})
    await session.execute(text("DELETE FROM users WHERE email = ANY(:emails)"), {"emails": list(_EMAILS.values())})
    await session.commit()


# Four groups:
#   * mine      — the user is admin; their seat is "Santi";
#   * shared    — the OTHER account is admin and the user a plain member, seated "Santi"; the other
#                 account's seat and a name-only placeholder are both "Santi" too;
#   * nickname  — the user's seat is "Nick";
#   * former    — the user left; their inactive seat is still "Santi".
@pytest_asyncio.fixture
async def seeded():
    admin_engine = create_async_engine(ADMIN_URL)
    app_engine = create_async_engine(APP_URL)
    app = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    admin = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)

    async with admin() as s:
        await _cleanup(s)
        users = {
            key: await _scalar(s, "INSERT INTO users (name, email, password_hash) VALUES ('Santi', :e, 'h') RETURNING id", e=email)
            for key, email in _EMAILS.items()
        }
        groups = {
            key: await _scalar(s, "INSERT INTO groups (name, kind, created_by) VALUES (:n, 'household', :u) RETURNING id", n=name, u=users["me"])
            for key, name in _GROUPS.items()
        }

        async def seat(group: str, user: str | None, name: str, role: str = "member", active: bool = True) -> int:
            return await _scalar(
                s,
                "INSERT INTO group_members (group_id, user_id, display_name, role, is_active) VALUES (:g, :u, :n, :r, :a) RETURNING id",
                g=groups[group],
                u=users[user] if user else None,
                n=name,
                r=role,
                a=active,
            )

        seats = {
            "mine": await seat("mine", "me", "Santi", "admin"),
            "shared": await seat("shared", "me", "Santi"),
            "shared_other": await seat("shared", "other", "Santi", "admin"),
            "shared_placeholder": await seat("shared", None, "Santi"),
            "nickname": await seat("nickname", "me", "Nick", "admin"),
            "former": await seat("former", "me", "Santi", active=False),
            "former_other": await seat("former", "other", "Santi", "admin"),
        }
        await s.commit()

    yield {"users": users, "groups": groups, "seats": seats, "app": app, "admin": admin}

    async with admin() as s:
        await _cleanup(s)
    await app_engine.dispose()
    await admin_engine.dispose()


# A request session for `key`: the restricted role, their context set, and their user row loaded through
# it — exactly what get_current_user leaves a route holding.
async def _request(seeded, session: AsyncSession, key: str) -> User:
    set_session_user(session, seeded["users"][key])
    return await session.get(User, seeded["users"][key])


async def _rename(seeded, name: str, *, rename_group_seats: bool = True) -> int:
    async with seeded["app"]() as s:
        user = await _request(seeded, s, "me")
        _, renamed = await user_account_service.update_profile(s, user, name, rename_group_seats=rename_group_seats)
        return renamed


async def _names(seeded) -> dict[str, str]:
    async with seeded["admin"]() as s:
        sql = text("SELECT id, display_name FROM group_members WHERE id = ANY(:ids)")
        by_id = dict((await s.execute(sql, {"ids": list(seeded["seats"].values())})).all())
        account = await _scalar(s, "SELECT name FROM users WHERE id = :u", u=seeded["users"]["me"])
    return {"account": account} | {key: by_id[seat_id] for key, seat_id in seeded["seats"].items()}


_UNTOUCHED = {
    "shared_other": "Santi",
    "shared_placeholder": "Santi",
    "nickname": "Nick",
    "former": "Santi",
    "former_other": "Santi",
}


class TestWhichSeats:
    @pytest.mark.asyncio
    async def test_lists_the_groups_where_the_users_active_seat_carries_the_account_name(self, seeded):
        async with seeded["app"]() as s:
            user = await _request(seeded, s, "me")
            groups = await user_account_service.list_groups_using_account_name(s, user)
        assert [group.id for group in groups] == [seeded["groups"]["mine"], seeded["groups"]["shared"]]

    @pytest.mark.asyncio
    async def test_renames_the_users_own_active_seats_and_no_one_elses(self, seeded):
        assert await _rename(seeded, "Santiago") == 2
        # Including the seat in a group the user does not administer: it is their own.
        assert await _names(seeded) == {"account": "Santiago", "mine": "Santiago", "shared": "Santiago"} | _UNTOUCHED

    @pytest.mark.asyncio
    async def test_each_rename_is_in_its_groups_feed_and_nobody_is_notified(self, seeded):
        await _rename(seeded, "Santiago")
        async with seeded["admin"]() as s:
            entries = (
                await s.execute(
                    text(
                        "SELECT group_id, entity_id, actor_user_id, payload->>'member', payload->>'variant' FROM shared_audit_log"
                        " WHERE group_id = ANY(:g) AND entity_type = 'group_member' AND action = 'updated' ORDER BY group_id"
                    ),
                    {"g": list(seeded["groups"].values())},
                )
            ).all()
            notified = await _scalar(s, "SELECT count(*) FROM notifications WHERE user_id = ANY(:u)", u=list(seeded["users"].values()))
        me = seeded["users"]["me"]
        assert entries == [
            (seeded["groups"]["mine"], seeded["seats"]["mine"], me, "Santiago", "account_name"),
            (seeded["groups"]["shared"], seeded["seats"]["shared"], me, "Santiago", "account_name"),
        ]
        assert notified == 0

    @pytest.mark.asyncio
    async def test_the_feed_entry_keeps_the_old_name_beside_the_live_actor(self, seeded):
        # Read back through the real activity read: its actor comes from the live roster, which after the
        # rename already says the new name, so only the payload can carry the old one.
        await _rename(seeded, "Santiago")
        async with seeded["app"]() as s:
            user = await _request(seeded, s, "me")
            entries = await shared_audit_service.list_activity(s, seeded["groups"]["shared"], user, limit=10)
        renamed = [entry for entry in entries if entry.payload.get("variant") == "account_name"]
        assert [(entry.actor_name, entry.payload["from"], entry.payload["member"]) for entry in renamed] == [("Santiago", "Santi", "Santiago")]

    @pytest.mark.asyncio
    async def test_without_the_flag_only_the_account_is_renamed(self, seeded):
        assert await _rename(seeded, "Santiago", rename_group_seats=False) == 0
        assert await _names(seeded) == {"account": "Santiago", "mine": "Santi", "shared": "Santi"} | _UNTOUCHED

    @pytest.mark.asyncio
    async def test_another_member_already_called_the_new_name_does_not_stop_it(self, seeded):
        # Seat names are not unique in a group, so nothing is skipped and nothing fails.
        async with seeded["admin"]() as s:
            await s.execute(text("UPDATE group_members SET display_name = 'Santiago' WHERE id = :m"), {"m": seeded["seats"]["shared_other"]})
            await s.commit()
        assert await _rename(seeded, "Santiago") == 2
        names = await _names(seeded)
        assert (names["shared"], names["shared_other"]) == ("Santiago", "Santiago")

    @pytest.mark.asyncio
    async def test_the_longest_name_the_account_accepts_fits_a_seat(self, seeded):
        name = "é" * 255
        assert await _rename(seeded, name) == 2
        names = await _names(seeded)
        assert (names["account"], names["mine"], names["shared"]) == (name, name, name)


class TestOneTransaction:
    @pytest.mark.asyncio
    async def test_a_failure_part_way_leaves_the_account_and_every_seat_as_they_were(self, seeded, monkeypatch):
        record = shared_audit_service.record
        calls = {"n": 0}

        async def fail_on_the_second(session, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("the second group's audit entry failed")
            return await record(session, **kwargs)

        monkeypatch.setattr(user_account_service.shared_audit_service, "record", fail_on_the_second)
        with pytest.raises(RuntimeError):
            await _rename(seeded, "Santiago")
        assert await _names(seeded) == {"account": "Santi", "mine": "Santi", "shared": "Santi"} | _UNTOUCHED


class TestRaces:
    @pytest.mark.asyncio
    async def test_an_admin_renaming_the_seat_meanwhile_keeps_their_name(self, seeded):
        async with seeded["app"]() as admin_request:
            set_session_user(admin_request, seeded["users"]["other"])
            # The admin's rename of the user's seat, written and not yet committed.
            await admin_request.execute(text("UPDATE group_members SET display_name = 'Santi B' WHERE id = :m"), {"m": seeded["seats"]["shared"]})
            rename = asyncio.create_task(_rename(seeded, "Santiago"))
            await asyncio.sleep(0.5)
            # Waiting on the seat, not deciding from a name that is about to change.
            assert not rename.done()
            await admin_request.commit()
            assert await rename == 1
        names = await _names(seeded)
        assert (names["account"], names["mine"], names["shared"]) == ("Santiago", "Santiago", "Santi B")

    @pytest.mark.asyncio
    async def test_a_rename_in_flight_is_waited_for_and_then_followed(self, seeded):
        async with seeded["app"]() as first:
            user = await _request(seeded, first, "me")
            # The first rename holds the seats and has renamed them and the account, uncommitted.
            await first.execute(
                text("SELECT id FROM group_members WHERE id = ANY(:ids) ORDER BY id FOR UPDATE"),
                {"ids": [seeded["seats"]["mine"], seeded["seats"]["shared"]]},
            )
            await first.execute(
                text("UPDATE group_members SET display_name = 'Santiago' WHERE id = ANY(:ids)"),
                {"ids": [seeded["seats"]["mine"], seeded["seats"]["shared"]]},
            )
            user.name = "Santiago"
            await first.flush()
            second = asyncio.create_task(_rename(seeded, "Sant"))
            await asyncio.sleep(0.5)
            assert not second.done()
            await first.commit()
            # The second matched the seats against "Santiago", the name the first left.
            assert await second == 2
        assert await _names(seeded) == {"account": "Sant", "mine": "Sant", "shared": "Sant"} | _UNTOUCHED

    @pytest.mark.asyncio
    async def test_a_request_that_loaded_the_old_name_matches_the_one_committed_since(self, seeded):
        async with seeded["app"]() as late:
            # Authenticated while the account was still "Santi" ...
            stale = await _request(seeded, late, "me")
            # ... and another rename committed before it got to the seats.
            assert await _rename(seeded, "Santiago") == 2
            _, renamed = await user_account_service.update_profile(late, stale, "Sant", rename_group_seats=True)
        assert renamed == 2
        assert await _names(seeded) == {"account": "Sant", "mine": "Sant", "shared": "Sant"} | _UNTOUCHED

    @pytest.mark.asyncio
    async def test_a_member_removed_while_the_rename_waits_keeps_their_seat_as_it_was(self, seeded):
        # The seat is read as active before the lock and is inactive once it is taken. The membership
        # policy then hides it from the user's own UPDATE, so only the re-check after the lock keeps the
        # rename from failing on it.
        async with seeded["app"]() as admin_request:
            set_session_user(admin_request, seeded["users"]["other"])
            await admin_request.execute(text("UPDATE group_members SET is_active = FALSE WHERE id = :m"), {"m": seeded["seats"]["shared"]})
            rename = asyncio.create_task(_rename(seeded, "Santiago"))
            await asyncio.sleep(0.5)
            assert not rename.done()
            await admin_request.commit()
            assert await rename == 1
        names = await _names(seeded)
        assert (names["account"], names["mine"], names["shared"]) == ("Santiago", "Santiago", "Santi")
