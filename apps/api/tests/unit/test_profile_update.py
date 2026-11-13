import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_admin_session, get_auth_session, get_session
from app.deps.auth import get_current_user
from app.main import create_app
from app.models.group import Group, GroupKind, GroupMember
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User, UserPlan
from app.rate_limit import CHANGE_NAME_LIMIT, limiter
from app.services import user_account_service

# PATCH /me renames the account: the name, trimmed, 1 to 255 characters, and on request the user's group
# seats that still carry the old name. It runs on the request session (RLS lets a user write only their
# own row, and seats only in groups they are an active member of), and answers with the user as
# GET /auth/me does plus the number of seats renamed. GET /me/name/groups lists the groups that would
# follow. The database half (the seat query's predicate, the locks, the rollback) is in
# tests/integration/test_account_rename_seats.py.


def _user() -> User:
    return User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0, plan=UserPlan.free)


def _client(sessions: dict, user: User) -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _request_session():
        sessions["kind"] = "request"
        yield AsyncMock()

    async def _admin_session():
        sessions["kind"] = "privileged"
        yield AsyncMock()

    app.dependency_overrides[get_session] = _request_session
    app.dependency_overrides[get_admin_session] = _admin_session
    app.dependency_overrides[get_auth_session] = _admin_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=False)


# The limiter's counts are shared in memory; each test starts from zero.
@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


class TestUpdateProfile:
    def test_renames_the_user_and_answers_with_the_new_name(self, monkeypatch):
        sessions: dict = {}
        user = _user()
        save = AsyncMock()
        monkeypatch.setattr(user_account_service.user_repository, "save", save)
        response = _client(sessions, user).patch("/me", json={"name": "  Santiago Alemarino  "})
        assert response.status_code == 200
        assert response.json()["name"] == "Santiago Alemarino"
        assert user.name == "Santiago Alemarino"
        save.assert_awaited_once()
        assert sessions["kind"] == "request"

    @pytest.mark.parametrize("name", ["", "   ", "x" * 256])
    def test_refuses_an_empty_or_overlong_name(self, monkeypatch, name):
        save = AsyncMock()
        monkeypatch.setattr(user_account_service.user_repository, "save", save)
        user = _user()
        response = _client({}, user).patch("/me", json={"name": name})
        assert response.status_code == 422
        assert user.name == "Santi"
        save.assert_not_awaited()

    def test_takes_nothing_but_the_name(self, monkeypatch):
        monkeypatch.setattr(user_account_service.user_repository, "save", AsyncMock())
        user = _user()
        response = _client({}, user).patch("/me", json={"name": "Santi", "email": "other@test"})
        assert response.status_code == 200
        assert user.email == "u@test"

    def test_is_rate_limited_per_user(self, monkeypatch):
        # The same bound as the other account writes: five an hour, then 429.
        monkeypatch.setattr(user_account_service.user_repository, "save", AsyncMock())
        assert CHANGE_NAME_LIMIT == "5/hour"
        client = _client({}, _user())
        statuses = [client.patch("/me", json={"name": f"Santi {n}"}).status_code for n in range(6)]
        assert statuses == [200] * 5 + [429]


def _seat(seat_id: int, group_id: int, name: str, *, is_active: bool = True) -> GroupMember:
    return GroupMember(id=seat_id, group_id=group_id, user_id=1, display_name=name, is_active=is_active)


# Stubs every repository and the audit trail the seat rename reaches, and records what reached them.
def _stub_seats(monkeypatch, seats: list[GroupMember], *, on_seat_lock=None, on_user_lock=None) -> dict:
    calls: dict = {"locked_seats": None, "user_locked": False, "audit": [], "listed": False}

    async def list_active_members(session, user_id):
        calls["listed"] = True
        return seats

    async def lock_members(session, member_ids, *, shared=False):
        calls["locked_seats"] = (list(member_ids), shared, calls["user_locked"])
        if on_seat_lock:
            on_seat_lock()

    async def lock_user(session, user_id):
        calls["user_locked"] = True
        if on_user_lock:
            on_user_lock()

    async def record(session, **kwargs):
        calls["audit"].append(kwargs)

    monkeypatch.setattr(user_account_service.group_repository, "list_active_members", list_active_members)
    monkeypatch.setattr(user_account_service.group_repository, "lock_members", lock_members)
    monkeypatch.setattr(user_account_service.group_repository, "save_member", AsyncMock())
    monkeypatch.setattr(user_account_service.user_repository, "lock", lock_user)
    monkeypatch.setattr(user_account_service.user_repository, "save", AsyncMock())
    monkeypatch.setattr(user_account_service.shared_audit_service, "record", record)
    return calls


class TestRenameGroupSeats:
    def test_renames_only_the_seats_still_carrying_the_old_name(self, monkeypatch):
        seats = [
            _seat(11, 1, "Santi"),
            _seat(12, 2, "Santi"),
            _seat(13, 3, "Nick"),
            _seat(14, 4, "santi"),
            _seat(15, 5, "Santiago"),
        ]
        calls = _stub_seats(monkeypatch, seats)
        response = _client({}, _user()).patch("/me", json={"name": "Santiago", "rename_group_seats": True})
        assert response.status_code == 200
        assert response.json()["name"] == "Santiago"
        assert response.json()["group_seats_renamed"] == 2
        # A nickname and a different casing are the group's own; a seat already called the new name
        # did not carry the old one, so it is neither counted nor touched.
        assert [seat.display_name for seat in seats] == ["Santiago", "Santiago", "Nick", "santi", "Santiago"]
        assert [(entry["group_id"], entry["entity_id"]) for entry in calls["audit"]] == [(1, 11), (2, 12)]

    def test_records_each_rename_in_its_group_feed_as_the_account_name_variant(self, monkeypatch):
        user = _user()
        calls = _stub_seats(monkeypatch, [_seat(11, 1, "Santi")])
        _client({}, user).patch("/me", json={"name": "Santiago", "rename_group_seats": True})
        assert calls["audit"] == [
            {
                "group_id": 1,
                "actor": user,
                "entity_type": AuditEntityType.group_member,
                "action": AuditAction.updated,
                "entity_id": 11,
                "payload": {"member": "Santiago", "variant": "account_name"},
            }
        ]

    def test_locks_the_seats_exclusively_and_before_the_user_row(self, monkeypatch):
        calls = _stub_seats(monkeypatch, [_seat(12, 2, "Santi"), _seat(11, 1, "Nick")])
        _client({}, _user()).patch("/me", json={"name": "Santiago", "rename_group_seats": True})
        # Every active seat, not only the matching ones: which match is decided after the lock re-reads.
        assert calls["locked_seats"] == ([12, 11], False, False)
        assert calls["user_locked"] is True

    def test_compares_with_the_trimming_names_get_on_the_way_in(self, monkeypatch):
        seats = [_seat(11, 1, "  Santi "), _seat(12, 2, "Santi")]
        _stub_seats(monkeypatch, seats)
        user = _user()
        user.name = "Santi  "
        response = _client({}, user).patch("/me", json={"name": "  Santiago  ", "rename_group_seats": True})
        assert response.json()["group_seats_renamed"] == 2
        assert [seat.display_name for seat in seats] == ["Santiago", "Santiago"]

    @pytest.mark.parametrize(
        "lookalike",
        [
            "SANTI",
            "Sant\u0131",  # dotless i
            "Santi\u200b",  # zero-width space, which no trimming removes
            "Jose\u0301",  # "José" decomposed, against an account name stored composed
        ],
    )
    def test_a_lookalike_name_is_not_the_account_name(self, monkeypatch, lookalike):
        user = _user()
        user.name = "Jos\u00e9" if lookalike.startswith("Jose") else "Santi"
        seats = [_seat(11, 1, lookalike)]
        _stub_seats(monkeypatch, seats)
        response = _client({}, user).patch("/me", json={"name": "Someone else", "rename_group_seats": True})
        assert response.json()["group_seats_renamed"] == 0
        assert seats[0].display_name == lookalike

    def test_a_user_in_no_group_is_simply_renamed(self, monkeypatch):
        calls = _stub_seats(monkeypatch, [])
        user = _user()
        response = _client({}, user).patch("/me", json={"name": "Santiago", "rename_group_seats": True})
        assert response.status_code == 200
        assert response.json()["group_seats_renamed"] == 0
        assert user.name == "Santiago"
        assert calls["audit"] == []

    def test_without_the_flag_no_seat_is_read_or_renamed(self, monkeypatch):
        seats = [_seat(11, 1, "Santi")]
        calls = _stub_seats(monkeypatch, seats)
        response = _client({}, _user()).patch("/me", json={"name": "Santiago"})
        assert response.json()["group_seats_renamed"] == 0
        assert seats[0].display_name == "Santi"
        assert (calls["listed"], calls["locked_seats"], calls["user_locked"]) == (False, None, False)

    def test_the_flag_is_ignored_when_the_name_does_not_change(self, monkeypatch):
        seats = [_seat(11, 1, "Santi")]
        calls = _stub_seats(monkeypatch, seats)
        response = _client({}, _user()).patch("/me", json={"name": " Santi ", "rename_group_seats": True})
        assert response.status_code == 200
        assert response.json()["group_seats_renamed"] == 0
        assert calls["audit"] == []

    def test_matches_the_name_the_lock_reads_rather_than_the_one_the_request_loaded(self, monkeypatch):
        # Another rename committed between this request authenticating and taking the lock: the seats now
        # carry "Santiago", and so does the account, which the lock re-reads.
        seats = [_seat(11, 1, "Santiago")]
        user = _user()
        _stub_seats(monkeypatch, seats, on_user_lock=lambda: setattr(user, "name", "Santiago"))
        response = _client({}, user).patch("/me", json={"name": "Sant", "rename_group_seats": True})
        assert response.json()["group_seats_renamed"] == 1
        assert seats[0].display_name == "Sant"

    def test_a_seat_an_admin_renamed_or_removed_while_waiting_is_left_as_they_left_it(self, monkeypatch):
        renamed_by_admin, removed = _seat(11, 1, "Santi"), _seat(12, 2, "Santi")
        kept = _seat(13, 3, "Santi")

        def admin_committed():
            renamed_by_admin.display_name = "Nick"
            removed.is_active = False

        _stub_seats(monkeypatch, [renamed_by_admin, removed, kept], on_seat_lock=admin_committed)
        response = _client({}, _user()).patch("/me", json={"name": "Santiago", "rename_group_seats": True})
        assert response.json()["group_seats_renamed"] == 1
        assert [seat.display_name for seat in (renamed_by_admin, removed, kept)] == ["Nick", "Santi", "Santiago"]

    def test_a_failure_part_way_commits_nothing(self, monkeypatch):
        _stub_seats(monkeypatch, [_seat(11, 1, "Santi"), _seat(12, 2, "Santi")])
        failures = iter([None, RuntimeError("audit insert failed")])

        async def record(session, **kwargs):
            failure = next(failures)
            if failure:
                raise failure

        monkeypatch.setattr(user_account_service.shared_audit_service, "record", record)
        session = AsyncMock()
        user = _user()
        with pytest.raises(RuntimeError):
            asyncio.run(user_account_service.update_profile(session, user, "Santiago", rename_group_seats=True))
        session.commit.assert_not_awaited()

    def test_a_255_character_name_reaches_the_seats_whole(self, monkeypatch):
        # The seat's display_name and the account name share one limit (VARCHAR(255) both), so any name
        # PATCH /me accepts fits a seat.
        assert GroupMember.model_fields["display_name"].metadata[0].max_length == 255
        seats = [_seat(11, 1, "Santi")]
        _stub_seats(monkeypatch, seats)
        name = "\u00e9" * 255
        response = _client({}, _user()).patch("/me", json={"name": name, "rename_group_seats": True})
        assert response.json()["group_seats_renamed"] == 1
        assert seats[0].display_name == name


class TestGroupsUsingAccountName:
    def test_lists_the_groups_whose_active_seat_carries_the_account_name_by_group_name(self, monkeypatch):
        sessions: dict = {}
        seats = [_seat(11, 1, "Santi"), _seat(12, 2, " Santi"), _seat(13, 3, "Nick"), _seat(14, 4, "santi")]
        asked: dict = {}

        async def list_active_members(session, user_id):
            return seats

        async def get_by_ids(session, group_ids):
            asked["ids"] = group_ids
            return [Group(id=1, name="Trip", kind=GroupKind.trip), Group(id=2, name="flat", kind=GroupKind.flat)]

        monkeypatch.setattr(user_account_service.group_repository, "list_active_members", list_active_members)
        monkeypatch.setattr(user_account_service.group_repository, "get_by_ids", get_by_ids)
        response = _client(sessions, _user()).get("/me/name/groups")
        assert response.status_code == 200
        assert asked["ids"] == [1, 2]
        assert response.json() == {"groups": [{"id": 2, "name": "flat"}, {"id": 1, "name": "Trip"}]}
        assert sessions["kind"] == "request"

    def test_a_user_in_no_group_gets_an_empty_list(self, monkeypatch):
        async def list_active_members(session, user_id):
            return []

        monkeypatch.setattr(user_account_service.group_repository, "list_active_members", list_active_members)
        monkeypatch.setattr(user_account_service.group_repository, "get_by_ids", AsyncMock(return_value=[]))
        assert _client({}, _user()).get("/me/name/groups").json() == {"groups": []}
