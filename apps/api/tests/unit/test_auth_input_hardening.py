import hashlib

import httpx
import pytest
from pydantic import ValidationError

from app.repositories import user_repository
from app.schemas.auth import MIN_PASSWORD_LENGTH, LoginRequest, RegisterRequest
from app.services import auth_service

# Input-hardening coverage for AUTH-3 (password policy + HIBP breach check) and
# AUTH-4 (email validation + lowercase normalization).

_VALID_PASSWORD = "correct horse battery staple"


# --- RegisterRequest password policy (AUTH-3) ---


class TestRegisterRequestPasswordPolicy:
    def test_password_below_minimum_rejected(self):
        # An 11-character password is one short of the 12-character minimum.
        with pytest.raises(ValidationError):
            RegisterRequest(name="Santi", email="user@example.com", password="elevenchar")

    def test_password_at_minimum_accepted(self):
        body = RegisterRequest(name="Santi", email="user@example.com", password="x" * MIN_PASSWORD_LENGTH)
        assert len(body.password) == MIN_PASSWORD_LENGTH


# --- Email validation and normalization (AUTH-4) ---


class TestEmailNormalization:
    def test_register_email_lowercased(self):
        # Case variants normalize to the same stored value so they map to one account.
        body = RegisterRequest(name="Santi", email="Foo@Example.COM", password=_VALID_PASSWORD)
        assert body.email == "foo@example.com"

    def test_login_email_lowercased(self):
        body = LoginRequest(email="Foo@Example.COM", password=_VALID_PASSWORD)
        assert body.email == "foo@example.com"

    def test_invalid_email_rejected(self):
        with pytest.raises(ValidationError):
            RegisterRequest(name="Santi", email="not-an-email", password=_VALID_PASSWORD)


# --- user_repository.get_by_email lowercasing (AUTH-4) ---


# Minimal result stub so the repository's scalar_one_or_none() call resolves.
class _StubResult:
    def scalar_one_or_none(self) -> None:
        return None


# Fake session that captures the executed statement instead of hitting a database.
class _CapturingSession:
    def __init__(self) -> None:
        self.statement = None

    async def execute(self, statement):
        self.statement = statement
        return _StubResult()


class TestGetByEmailLowercasing:
    @pytest.mark.asyncio
    async def test_email_lowercased_before_query(self):
        session = _CapturingSession()
        await user_repository.get_by_email(session, "Foo@Example.COM")
        values = list(session.statement.compile().params.values())
        assert "foo@example.com" in values
        assert "Foo@Example.COM" not in values


# --- HIBP breach check (AUTH-3) ---


# Fake httpx response exposing the range-API text body.
class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


# Builds a fake httpx.AsyncClient class returning body / raising error, recording the URL.
def _make_fake_client(*, body: str | None = None, error: Exception | None = None, captured: list[str] | None = None):
    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> bool:
            return False

        async def get(self, url: str) -> _FakeResponse:
            if captured is not None:
                captured.append(url)
            if error is not None:
                raise error
            return _FakeResponse(body or "")

    return _FakeAsyncClient


class TestIsPasswordBreached:
    @pytest.mark.asyncio
    async def test_flags_known_breached_password(self, monkeypatch):
        # "password" hashes to a digest whose suffix is present in the mocked range response.
        digest = hashlib.sha1(b"password").hexdigest().upper()
        prefix, suffix = digest[:5], digest[5:]
        body = f"0018A45C4D1DEF81644B54AB7F969B88D65:3\r\n{suffix}:9659365\r\nABCDEF0123456789ABCDEF0123456789ABCD:2"
        captured: list[str] = []
        monkeypatch.setattr(auth_service.httpx, "AsyncClient", _make_fake_client(body=body, captured=captured))

        assert await auth_service.is_password_breached("password") is True
        # k-anonymity: only the 5-char prefix leaves the process.
        assert captured[0].endswith(prefix)
        assert suffix not in captured[0]

    @pytest.mark.asyncio
    async def test_allows_password_absent_from_breach_list(self, monkeypatch):
        body = "0018A45C4D1DEF81644B54AB7F969B88D65:3\r\nABCDEF0123456789ABCDEF0123456789ABCD:1"
        monkeypatch.setattr(auth_service.httpx, "AsyncClient", _make_fake_client(body=body))

        assert await auth_service.is_password_breached("password") is False

    @pytest.mark.asyncio
    async def test_fails_open_when_api_unreachable(self, monkeypatch):
        # An HIBP outage must not block signup.
        monkeypatch.setattr(auth_service.httpx, "AsyncClient", _make_fake_client(error=httpx.ConnectError("simulated outage")))

        assert await auth_service.is_password_breached("password") is False
