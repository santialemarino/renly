from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_admin_session, get_session
from app.deps.auth import get_current_user
from app.main import create_app
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.user import User
from app.services import group_invite_service, group_service

# Route-level contracts that live in the ROUTER rather than in a service, and that therefore no service
# test can protect. Two of them are load-bearing enough to pin:
#
#   * which session each endpoint is handed. The two RLS-bootstrap use cases need the privileged one,
#     and swapping either to SessionDep leaves every service test green while the endpoint fails against
#     a real database (proven separately in tests/integration/test_rls_isolation.py, which is where the
#     policy actually refuses it — here we pin the wiring itself, which is cheap and catches it first).
#   * whether an endpoint requires a session at all. The invite PREVIEW must not: a recipient opens the
#     link with no session, and adding auth to it would bounce every one of them to /login and drop the
#     token. Nothing else in the suite would notice.

USER = User(id=1, name="Santi", email="u@test", password_hash="x", session_epoch=0)
_GROUP = Group(id=10, name="Casa", kind=GroupKind.household, created_by=USER.id)
_SEAT = GroupMember(id=1, group_id=10, user_id=USER.id, display_name="Santi", role=GroupMemberRole.admin)


# Builds the real app with the DB and auth dependencies faked, so a request exercises the router's own
# wiring. `sessions` records which override each endpoint actually resolved.
def _client(sessions: dict, *, authenticated: bool = True) -> TestClient:
    app = create_app(Settings(database_url="postgresql+asyncpg://u:p@localhost:5432/renly", jwt_secret="x" * 32))

    async def _request_session():
        sessions["kind"] = "request"
        yield AsyncMock()

    async def _admin_session():
        sessions["kind"] = "privileged"
        yield AsyncMock()

    app.dependency_overrides[get_session] = _request_session
    app.dependency_overrides[get_admin_session] = _admin_session
    if authenticated:
        app.dependency_overrides[get_current_user] = lambda: USER
    return TestClient(app, raise_server_exceptions=False)


class TestSessionWiring:
    @pytest.mark.asyncio
    async def test_creating_a_group_is_handed_the_privileged_session(self, monkeypatch):
        sessions: dict = {}
        monkeypatch.setattr(
            group_service,
            "create_group",
            AsyncMock(return_value=group_service._build_response(_GROUP, [_SEAT], set(), _SEAT)),
        )
        response = _client(sessions).post("/groups", json={"name": "Casa", "kind": "household"})
        assert response.status_code == 201
        assert sessions["kind"] == "privileged"

    @pytest.mark.asyncio
    async def test_claiming_an_invite_is_handed_the_privileged_session(self, monkeypatch):
        # The other half of the bootstrap: the redeemer is not a member yet, so the membership policy
        # hides the invite row from the request session and the claim would simply never find it.
        sessions: dict = {}
        monkeypatch.setattr(
            group_invite_service,
            "accept_invite",
            AsyncMock(return_value={"group_id": 10, "group_name": "Casa", "member_id": 1}),
        )
        response = _client(sessions).post("/group-invites/tok/accept")
        assert response.status_code == 200
        assert sessions["kind"] == "privileged"

    @pytest.mark.asyncio
    async def test_reading_a_group_is_handed_the_request_session(self, monkeypatch):
        # The counterweight: everything that is NOT the bootstrap must stay under RLS, or the perimeter
        # quietly widens one endpoint at a time.
        sessions: dict = {}
        monkeypatch.setattr(
            group_service,
            "get_group",
            AsyncMock(return_value=group_service._build_response(_GROUP, [_SEAT], set(), _SEAT)),
        )
        assert _client(sessions).get("/groups/10").status_code == 200
        assert sessions["kind"] == "request"


class TestInvitePreviewNeedsNoSession:
    @pytest.mark.asyncio
    async def test_the_preview_is_reachable_with_no_authorization_header(self, monkeypatch):
        # Most recipients open a join link logged out. If this endpoint ever grows a CurrentUser
        # dependency they all get a 401 instead of the invite, and the public /join page is pointless.
        monkeypatch.setattr(
            group_invite_service,
            "preview_invite",
            AsyncMock(
                return_value={
                    "group_name": "Casa",
                    "group_kind": "household",
                    "member_display_name": "Ana",
                    "invited_by_name": "Santi",
                    "expires_at": "2026-09-01T00:00:00",
                }
            ),
        )
        response = _client({}, authenticated=False).get("/group-invites/tok")
        assert response.status_code == 200
        assert response.json()["group_name"] == "Casa"

    @pytest.mark.asyncio
    async def test_claiming_a_seat_still_requires_a_session(self, monkeypatch):
        # The preview being open must not make the CLAIM open: the token says which seat, the session
        # says whose it becomes, so without one there is nobody to link.
        called = AsyncMock()
        monkeypatch.setattr(group_invite_service, "accept_invite", called)
        response = _client({}, authenticated=False).post("/group-invites/tok/accept")
        assert response.status_code == 401
        called.assert_not_awaited()
