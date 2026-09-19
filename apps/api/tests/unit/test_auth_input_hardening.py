import hashlib

import bcrypt
import httpx
import pytest
from pydantic import AfterValidator, BaseModel, ValidationError

from app.repositories import user_repository
from app.schemas import auth as auth_schemas
from app.schemas import user_account as user_account_schemas
from app.schemas.auth import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH, LoginRequest, RegisterRequest, _within_bcrypt_limit
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


# --- bcrypt's 72-byte ceiling (the cap that keeps an over-long password out of a 500) ---


# A password bcrypt CAN hash, and three it cannot — each one a shape a real person would pick.
#
# The accented and emoji cases are the point of the whole section: they are 40 and 20 CHARACTERS, so a
# `max_length=72` field would accept all three and hand them straight to bcrypt. This is an es-locale
# app, so an accented passphrase is the ordinary case.
_AT_LIMIT = "a" * MAX_PASSWORD_BYTES
_OVER_BY_ONE = "a" * (MAX_PASSWORD_BYTES + 1)
_ACCENTED_OVER = "á" * 40  # 40 characters, 80 bytes
_EMOJI_OVER = "🙂" * 20  # 20 characters, 80 bytes


class TestPasswordByteCeiling:
    def test_a_password_at_the_limit_is_accepted(self):
        body = RegisterRequest(name="Santi", email="user@example.com", password=_AT_LIMIT)
        assert len(body.password.encode("utf-8")) == MAX_PASSWORD_BYTES

    @pytest.mark.parametrize("password", [_OVER_BY_ONE, _ACCENTED_OVER, _EMOJI_OVER])
    def test_an_over_long_password_is_refused_by_the_schema(self, password):
        # 422 at the edge rather than a ValueError out of bcrypt, which the app answers as a 500.
        with pytest.raises(ValidationError):
            RegisterRequest(name="Santi", email="user@example.com", password=password)

    @pytest.mark.parametrize("password", [_OVER_BY_ONE, _ACCENTED_OVER, _EMOJI_OVER])
    def test_login_refuses_the_same_passwords(self, password):
        # Login is the unauthenticated one, so it is the shape anybody can fire at the API. It reaches
        # bcrypt even for an unknown email, via the timing-equalisation dummy verify.
        with pytest.raises(ValidationError):
            LoginRequest(email="user@example.com", password=password)

    @pytest.mark.parametrize("password", [_OVER_BY_ONE, _ACCENTED_OVER, _EMOJI_OVER])
    def test_the_refused_passwords_are_exactly_the_ones_bcrypt_cannot_hash(self, password):
        # Ties the cap to its REASON rather than to a number restated here: if bcrypt's own limit ever
        # moves, this fails and says so, instead of the constant quietly describing nothing.
        with pytest.raises(ValueError):
            bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(4))

    def test_bcrypt_accepts_the_password_at_the_limit(self):
        # The other half of the pair: the cap must not be stricter than bcrypt either.
        assert bcrypt.hashpw(_AT_LIMIT.encode("utf-8"), bcrypt.gensalt(4))


class TestEveryPasswordFieldCarriesTheCeiling:
    # Derived from the schema modules rather than listed, because the defect being guarded is a field
    # that does not carry the rule — and a hand-written list is exactly how the seven existing fields
    # all came to be missing it.
    def _password_fields(self):
        found = []
        for module in (auth_schemas, user_account_schemas):
            for name in dir(module):
                model = getattr(module, name)
                if not (isinstance(model, type) and issubclass(model, BaseModel)):
                    continue
                for field_name, field in model.model_fields.items():
                    if "password" in field_name and "token" not in field_name:
                        found.append((model.__name__, field_name, field))
        return found

    def test_the_scan_finds_every_known_password_field(self):
        # Anti-vacuity: without this, a scan that stopped matching would make the assertion below pass
        # over an empty list. Seven is what the codebase has today; a new one raises this number.
        fields = self._password_fields()
        assert len(fields) >= 7, f"scan found only {len(fields)} password fields: {fields}"

    def test_every_password_field_is_capped_at_bcrypts_limit(self):
        missing = [
            f"{model}.{field_name}"
            for model, field_name, field in self._password_fields()
            if not any(isinstance(m, AfterValidator) and m.func is _within_bcrypt_limit for m in field.metadata)
        ]
        assert missing == [], f"password fields that can still reach bcrypt over its limit: {missing}"


# --- The 422 body must not echo what was submitted ---


class TestAValidationErrorNeverEchoesTheSubmittedValue:
    # FastAPI's default validation handler puts the offending value in an `input` key, so a refused
    # password came back in the response body — into browser devtools, any client-side error
    # reporting, and anything that records response bodies. `POST /auth/register` has always done
    # this for a too-short password; capping the length gave `POST /auth/login` the same trigger, and
    # that one is unauthenticated.
    #
    # Driven through the real app rather than by calling the handler, because what is being asserted
    # is the SHAPE OF THE RESPONSE a caller actually receives.

    @staticmethod
    def _client():
        from fastapi.testclient import TestClient

        from app.main import app

        return TestClient(app, raise_server_exceptions=False)

    def test_a_refused_password_does_not_come_back_in_the_response(self):
        secret = "aaaaaaaaaaaaaaaaaaaa-THE-PASSWORD-" + "z" * 60  # over the byte ceiling
        response = self._client().post("/auth/login", json={"email": "nobody@example.com", "password": secret})

        assert response.status_code == 422
        assert secret not in response.text, "the submitted password was echoed back in the 422 body"

    def test_a_too_short_password_does_not_come_back_either(self):
        # The pre-existing trigger, pinned in the same place so neither can regress alone.
        secret = "shortpw1234"
        response = self._client().post("/auth/register", json={"name": "X", "email": "nobody@example.com", "password": secret})

        assert response.status_code == 422
        assert secret not in response.text

    def test_the_422_still_says_which_field_and_why(self):
        # Stripping the value must not blind the caller: without loc/msg a client cannot tell the user
        # which field to fix, and the fix would have traded one defect for another.
        response = self._client().post("/auth/login", json={"email": "nobody@example.com", "password": "a" * 200})

        body = response.json()
        assert isinstance(body["detail"], list) and body["detail"], "the error list went missing"
        first = body["detail"][0]
        assert first["loc"][-1] == "password"
        assert "72 bytes" in first["msg"]
        assert "input" not in first
