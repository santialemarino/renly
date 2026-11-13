from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.db import get_admin_session, get_auth_session, get_session
from app.deps.auth import get_current_user
from app.main import create_app
from app.models.user import User, UserPlan
from app.rate_limit import CHANGE_NAME_LIMIT, limiter
from app.services import user_account_service

# PATCH /me renames the account: the name only, trimmed, 1 to 255 characters. It runs on the request
# session (RLS lets a user write only their own row), and answers with the user as GET /auth/me does.


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
