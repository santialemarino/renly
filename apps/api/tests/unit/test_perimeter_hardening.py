import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.config import Environment, Settings, SignupMode
from app.db import get_admin_session, get_session
from app.main import create_app
from app.middleware import MAX_REQUEST_BODY_BYTES
from app.models.user import User
from app.models.utils import utcnow
from app.rate_limit import client_ip, limiter
from app.services import auth_service

# Perimeter-hardening coverage for the M1 bundle: rate limiting + 429 (SEC-1), docs lockdown
# (SEC-7), catch-all 500 handler (SEC-8), env-driven CORS (SEC-9), request body-size limit
# (SEC-12), and register anti-enumeration (AUTH-5, M1 part).

_DB_URL = "postgresql+asyncpg://user:pass@localhost:5432/renly"
_SECRET = "x" * 32
_PASSWORD = "correct horse battery staple"


def _settings(**overrides) -> Settings:
    return Settings(database_url=_DB_URL, jwt_secret=_SECRET, **overrides)


# Stub HIBP breach check (no network) — treats every password as clean.
async def _not_breached(_plain: str) -> bool:
    return False


# Fake email adapter recording the messages it would send instead of hitting a provider.
class _FakeEmailService:
    def __init__(self, sent: list) -> None:
        self._sent = sent

    async def send(self, message) -> None:
        self._sent.append(message)


# Builds a TestClient over a fresh app, stubbing the DB session so auth routes need no database.
def _client(*, settings: Settings | None = None, existing_user: User | None = None) -> TestClient:
    app = create_app(settings or _settings())

    class _Result:
        def scalar_one_or_none(self):
            return existing_user

    class _Session:
        async def execute(self, *args, **kwargs):
            return _Result()

        def add(self, _obj):
            return None  # login now persists a refresh token (AUTH-7); no real DB here

        async def flush(self):
            return None

        async def commit(self):
            return None

    async def _fake_session():
        yield _Session()

    # login/register read users on the privileged session (pre-auth, RLS-bypassing); override both.
    app.dependency_overrides[get_session] = _fake_session
    app.dependency_overrides[get_admin_session] = _fake_session
    return TestClient(app, raise_server_exceptions=False)


# Resets the shared in-memory limiter before each test so request counts don't leak across tests.
@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


# --- SEC-1: rate limiting + 429 handler ---


class TestRateLimiting:
    def test_exceeding_login_limit_returns_429(self):
        client = _client()
        # The first LOGIN_LIMIT (5/min) attempts pass auth (401, no user); the next is throttled.
        statuses = [client.post("/auth/login", json={"email": "a@b.com", "password": _PASSWORD}).status_code for _ in range(6)]
        assert statuses[:5] == [401, 401, 401, 401, 401]
        assert statuses[5] == 429

    def test_429_body_is_generic_and_sets_retry_after(self):
        client = _client()
        for _ in range(5):
            client.post("/auth/login", json={"email": "a@b.com", "password": _PASSWORD})
        response = client.post("/auth/login", json={"email": "a@b.com", "password": _PASSWORD})
        assert response.status_code == 429
        assert response.json() == {"detail": "Too many requests. Please slow down and try again later."}
        assert response.headers.get("retry-after") is not None

    def test_health_is_exempt_from_rate_limiting(self):
        client = _client()
        # The global default is 100/min; /health must stay reachable well past it for uptime checks.
        assert all(client.get("/health").status_code == 200 for _ in range(110))

    def test_successful_login_returns_token_with_ratelimit_headers(self):
        # Regression: with headers_enabled the limiter injects X-RateLimit-* into the response, so a
        # rate-limited route must expose a Response param — otherwise a *successful* login 500s.
        # email_verified_at must be set: login is gated on a verified email (AUTH-1).
        user = User(
            id=1,
            name="Santi",
            email="me@example.com",
            session_epoch=0,
            password_hash=auth_service.hash_password(_PASSWORD),
            email_verified_at=utcnow(),
        )
        client = _client(existing_user=user)
        response = client.post("/auth/login", json={"email": "me@example.com", "password": _PASSWORD})
        assert response.status_code == 200
        assert response.json()["access_token"]
        assert response.headers.get("x-ratelimit-limit") is not None


# --- SEC-7: docs lockdown in production ---


class TestDocsLockdown:
    def test_docs_disabled_in_production(self):
        app = create_app(_settings(environment=Environment.production))
        assert app.docs_url is None
        assert app.redoc_url is None
        assert app.openapi_url is None

    def test_docs_enabled_outside_production(self):
        app = create_app(_settings(environment=Environment.development))
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"
        assert app.openapi_url == "/openapi.json"


# --- SEC-8: catch-all 500 handler + debug off in prod ---


class TestUnhandledExceptionHandler:
    def test_debug_off_in_production_on_in_development(self):
        assert _settings(environment=Environment.production).debug is False
        assert _settings(environment=Environment.development).debug is True

    def test_unhandled_error_returns_generic_500_without_trace(self):
        app = create_app(_settings(environment=Environment.production))

        @app.get("/_boom")
        def _boom():
            raise RuntimeError("sensitive stack detail")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/_boom")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error."}
        assert "sensitive stack detail" not in response.text


# --- SEC-9: env-driven CORS origins ---


class TestCorsOrigins:
    def test_comma_separated_origins_parsed(self):
        settings = _settings(cors_origins="https://app.renly.com, https://renly.com ,")
        assert settings.cors_origins == ["https://app.renly.com", "https://renly.com"]

    def test_default_origin_is_localhost(self):
        assert _settings().cors_origins == ["http://localhost:3000"]

    def test_allowed_origin_reflected_disallowed_omitted(self):
        client = _client(settings=_settings(cors_origins="https://app.renly.com"))
        allowed = client.options(
            "/auth/login",
            headers={"Origin": "https://app.renly.com", "Access-Control-Request-Method": "POST"},
        )
        assert allowed.headers.get("access-control-allow-origin") == "https://app.renly.com"
        disallowed = client.options(
            "/auth/login",
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        assert disallowed.headers.get("access-control-allow-origin") is None


# --- SEC-12: request body-size limit ---


class TestBodySizeLimit:
    def test_oversized_body_rejected_with_413(self):
        client = _client()
        response = client.post(
            "/auth/login",
            content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 413
        assert response.json() == {"detail": "Request body too large."}

    def test_normal_body_not_blocked(self):
        client = _client()
        # A normal small body passes the size middleware (reaches the handler → 401 for unknown user).
        response = client.post("/auth/login", json={"email": "a@b.com", "password": _PASSWORD})
        assert response.status_code == 401

    def test_oversized_chunked_body_rejected_with_413(self):
        client = _client()

        # A generator body makes httpx use Transfer-Encoding: chunked (no Content-Length), so the
        # declared-length fast path is skipped and the streaming byte counter must catch it.
        def _stream():
            yield b"x" * (MAX_REQUEST_BODY_BYTES + 1)

        response = client.post("/auth/login", content=_stream(), headers={"content-type": "application/json"})
        assert response.status_code == 413
        assert response.json() == {"detail": "Request body too large."}


# --- SEC-1 (follow-up): client IP behind a reverse proxy ---


def _request(headers: dict[str, str], peer: str) -> Request:
    raw = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    return Request({"type": "http", "headers": raw, "client": (peer, 0)})


class TestClientIpResolution:
    def test_direct_ignores_forwarded_header(self, monkeypatch):
        monkeypatch.setattr("app.rate_limit.settings", _settings(trusted_proxy_count=0))
        # Reached directly: X-Forwarded-For is attacker-controlled and must be ignored.
        assert client_ip(_request({"X-Forwarded-For": "1.2.3.4"}, "10.0.0.1")) == "10.0.0.1"

    def test_behind_one_proxy_reads_real_client(self, monkeypatch):
        monkeypatch.setattr("app.rate_limit.settings", _settings(trusted_proxy_count=1))
        assert client_ip(_request({"X-Forwarded-For": "1.2.3.4"}, "10.0.0.1")) == "1.2.3.4"

    def test_prepended_spoof_entries_ignored(self, monkeypatch):
        monkeypatch.setattr("app.rate_limit.settings", _settings(trusted_proxy_count=1))
        # The client prepends fake IPs; counting one hop from the right still yields the proxy-appended IP.
        forwarded = {"X-Forwarded-For": "9.9.9.9, 8.8.8.8, 1.2.3.4"}
        assert client_ip(_request(forwarded, "10.0.0.1")) == "1.2.3.4"


# --- AUTH-5 (completed in M2): register returns a uniform 202 and never leaks email existence ---


class TestRegisterAntiEnumeration:
    def test_duplicate_email_returns_uniform_202(self, monkeypatch):
        # No network: stub the HIBP breach check and the email send.
        monkeypatch.setattr("app.services.auth_service.is_password_breached", _not_breached)
        sent: list = []
        monkeypatch.setattr("app.services.auth_service.get_email_service", lambda: _FakeEmailService(sent))

        existing = User(id=1, name="Santi", email="taken@example.com", password_hash="hash")
        # Anti-enumeration is an open-registration property; the invite-only gate has its own
        # coverage (test_invites.py), so run this in open mode (auth_service reads the global settings).
        monkeypatch.setattr("app.config.settings.signup_mode", SignupMode.open)
        client = _client(existing_user=existing)
        response = client.post(
            "/auth/register",
            json={"name": "Santi", "email": "taken@example.com", "password": _PASSWORD},
        )
        assert response.status_code == 202
        # The body must not confirm the address is registered — just a generic acknowledgement.
        body = response.json()
        assert "registered" not in body["detail"].lower()
        # The existing address is emailed the "you already have an account" notice, not a leak.
        assert len(sent) == 1
        assert sent[0].to == "taken@example.com"
