import bcrypt
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, SignupMode
from app.config import settings as app_settings
from app.db import get_admin_session, get_session
from app.main import create_app
from app.rate_limit import limiter
from app.services import api_key_service, auth_service

# Coverage for the admin-pool connection-lifetime hardening (audit follow-up item 7): login,
# register, and API-key verification each run the ~250ms threaded bcrypt on the small shared admin
# pool. Each must RELEASE its connection (session.commit) BEFORE the hash so an auth burst can't pin
# the pool across the CPU-bound work and queue on pool_timeout. These tests pin the ordering:
# commit precedes the bcrypt call on every path. The bcrypt itself is stubbed to keep them fast.

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"
_SECRET = "x" * 32
_PASSWORD = "correct horse battery staple"
_PASSWORD_HASH = bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt()).decode()


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


class _RecordingResult:
    def __init__(self, value) -> None:
        self._value = value

    def scalar_one_or_none(self):
        return self._value


# Session double that records commit() calls into a shared event list so a test can assert commit
# ordering relative to the (separately recorded) bcrypt call.
class _RecordingSession:
    def __init__(self, events: list[str], scalar=None) -> None:
        self._events = events
        self._scalar = scalar

    async def execute(self, *args, **kwargs):
        return _RecordingResult(self._scalar)

    def add(self, _obj):
        return None

    async def flush(self):
        return None

    async def commit(self):
        self._events.append("commit")


class TestLoginReleasesConnectionBeforeBcrypt:
    def test_commit_precedes_bcrypt_on_unknown_email(self, monkeypatch):
        events: list[str] = []
        app = create_app(Settings(database_url=_DB_URL, jwt_secret=_SECRET))

        async def _fake_session():
            yield _RecordingSession(events, scalar=None)  # unknown email → no user row

        app.dependency_overrides[get_session] = _fake_session
        app.dependency_overrides[get_admin_session] = _fake_session

        orig_verify = auth_service.verify_password

        async def _spy_verify(plain, hashed):
            events.append("bcrypt")
            return await orig_verify(plain, hashed)

        monkeypatch.setattr(auth_service, "verify_password", _spy_verify)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/auth/login", json={"email": "nobody@example.com", "password": _PASSWORD})

        assert response.status_code == 401
        assert "commit" in events and "bcrypt" in events
        assert events.index("commit") < events.index("bcrypt")


class TestRegisterReleasesConnectionBeforeBcrypt:
    @pytest.mark.asyncio
    async def test_commit_precedes_hash(self, monkeypatch):
        events: list[str] = []

        class _FakeUserRepo:
            async def get_by_email(self, session, email):
                return None  # new address → create path

            async def create(self, session, user):
                user.id = 1
                return user

        async def _spy_hash(plain):
            events.append("bcrypt")
            return _PASSWORD_HASH

        async def _issue(*args, **kwargs):
            return "raw-token"

        async def _noop_send(_message):
            return None

        async def _not_breached(_plain):
            return False

        monkeypatch.setattr(app_settings, "signup_mode", SignupMode.open)
        monkeypatch.setattr(auth_service, "user_repository", _FakeUserRepo())
        monkeypatch.setattr(auth_service, "is_password_breached", _not_breached)
        monkeypatch.setattr(auth_service, "hash_password", _spy_hash)
        monkeypatch.setattr(auth_service, "issue_token", _issue)
        monkeypatch.setattr(auth_service, "_safe_send", _noop_send)

        session = _RecordingSession(events)
        await auth_service.register_account(session, "Santi", "new@example.com", _PASSWORD)

        assert events.index("commit") < events.index("bcrypt")


class TestVerifyApiKeyReleasesConnectionBeforeBcrypt:
    @pytest.mark.asyncio
    async def test_commit_precedes_bcrypt(self, monkeypatch):
        events: list[str] = []

        class _FakeKey:
            key_hash = _PASSWORD_HASH
            user_id = 1

        class _FakeApiKeyRepo:
            async def list_active_by_prefix(self, session, prefix):
                return [_FakeKey()]

            async def save(self, session, key):
                return None

        def _spy_checkpw(raw, hashed):
            events.append("bcrypt")
            return False  # no match → loop ends, no user lookup

        monkeypatch.setattr(api_key_service, "api_key_repository", _FakeApiKeyRepo())
        monkeypatch.setattr(api_key_service, "checkpw", _spy_checkpw)

        session = _RecordingSession(events)
        result = await api_key_service.verify_api_key(session, "rawkeyrawkeyrawkey")

        assert result is None
        assert events.index("commit") < events.index("bcrypt")
