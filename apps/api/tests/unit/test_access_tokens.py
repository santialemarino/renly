# The access token: what the API mints, what it accepts, and what every token-reading path refuses.
#
# The signer moved from python-jose to PyJWT, and a deploy must not log anyone out or let anyone in who
# was refused before. Two tokens below were minted by python-jose 3.5.0 BEFORE the swap, with the same
# claims `create_access_token` writes. The live one must still authenticate, and the token the current
# code mints for the same claims must be the same string byte for byte — which is also what proves the
# reverse direction, since python-jose accepted exactly that string.
#
# The refusal matrix runs through all three readers (the JWT-only dependency, the JWT-or-API-key one and
# the rate-limit key), because each catches the decode error itself and a reader that caught the wrong
# exception class would let the error escape as a 500 — or, worse, accept the token.

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from app.deps import api_key_auth, auth
from app.http_errors import CodedHTTPException
from app.models.user import User
from app.rate_limit import rate_limit_key
from app.services import api_key_service, auth_service

_SECRET = "u32b-compat-fixture-secret-not-a-real-one-0123456789"
# 2100-01-01T00:00:00Z, so the live fixture never expires under the suite.
_FAR_EXP = 4102444800
_CLAIMS = {"sub": "42", "email": "compat@example.com", "session_epoch": 3}

# Minted by python-jose 3.5.0: jwt.encode({**_CLAIMS, "exp": ...}, _SECRET, algorithm="HS256").
_JOSE_LIVE = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MiIsImVtYWlsIjoiY29tcGF0QGV4YW1wbGUuY29tIiwic2Vzc2lvbl9lcG9jaCI6MywiZXhwIjo0MTAy"
    "NDQ0ODAwfQ.qrDxWFpZk7U1sUwtgUiVZ7-2osug7N-wt_ZUwhNoyC0"
)
_JOSE_EXPIRED = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI0MiIsImVtYWlsIjoiY29tcGF0QGV4YW1wbGUuY29tIiwic2Vzc2lvbl9lcG9jaCI6MywiZXhwIjoxNzAw"
    "MDAwMDAwfQ.MovmMRzsxWqf60LO4QgJBWO7WTPMoMdxl26LiUJQ_ec"
)


def _b64(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data, separators=(",", ":")).encode()).rstrip(b"=").decode()


def _hs(claims: dict, *, key: str = _SECRET) -> str:
    return jwt.encode(claims, key, algorithm="HS256")


# HS512 signed by hand with the right secret: PyJWT would warn that the secret is short for SHA-512.
def _hs512(claims: dict) -> str:
    signing_input = f"{_b64({'alg': 'HS512', 'typ': 'JWT'})}.{_b64(claims)}"
    signature = hmac.new(_SECRET.encode(), signing_input.encode(), hashlib.sha512).digest()
    return f"{signing_input}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"


def _unsigned(claims: dict) -> str:
    return f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."


def _tampered() -> str:
    header, _, signature = _JOSE_LIVE.split(".")
    return f"{header}.{_b64({**_CLAIMS, 'sub': '43', 'exp': _FAR_EXP})}.{signature}"


# Every token here is refused by every reader. Built lazily so each case documents its own shape.
_REFUSED = {
    "expired (minted by python-jose)": lambda: _JOSE_EXPIRED,
    "expired": lambda: _hs({**_CLAIMS, "exp": 1_700_000_000}),
    "signed with another secret": lambda: _hs({**_CLAIMS, "exp": _FAR_EXP}, key="not-the-secret-" * 3),
    "payload edited after signing": _tampered,
    "right secret, wrong HMAC alg": lambda: _hs512({**_CLAIMS, "exp": _FAR_EXP}),
    "alg none, unsigned": lambda: _unsigned({**_CLAIMS, "exp": _FAR_EXP}),
    "asymmetric alg (ES256)": lambda: jwt.encode({**_CLAIMS, "exp": _FAR_EXP}, ec.generate_private_key(ec.SECP256R1()), algorithm="ES256"),
    "no sub": lambda: _hs({"session_epoch": 3, "exp": _FAR_EXP}),
    "no session_epoch": lambda: _hs({"sub": "42", "exp": _FAR_EXP}),
    "non-numeric sub": lambda: _hs({**_CLAIMS, "sub": "abc", "exp": _FAR_EXP}),
    "sub not a string": lambda: _hs({**_CLAIMS, "sub": 42, "exp": _FAR_EXP}),
    "an audience nobody asked for": lambda: _hs({**_CLAIMS, "exp": _FAR_EXP, "aud": "elsewhere"}),
    "not a JWT": lambda: "not-a-jwt",
}


# A request session that hands back the user the token names, recording every lookup.
class _Session:
    def __init__(self) -> None:
        self.info: dict = {}
        self.lookups: list[int] = []

    async def get(self, _model, user_id: int) -> User:
        self.lookups.append(user_id)
        return User(id=user_id, email="compat@example.com", name="x", password_hash="h", session_epoch=3)


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _request(token: str) -> Request:
    return Request({"type": "http", "headers": [(b"authorization", f"Bearer {token}".encode())], "client": ("203.0.113.7", 0)})


@pytest.fixture(autouse=True)
def _signing_settings(monkeypatch):
    monkeypatch.setattr(auth_service.settings, "jwt_secret", _SECRET)
    monkeypatch.setattr(auth_service.settings, "jwt_algorithm", "HS256")
    monkeypatch.setattr(auth_service.settings, "trusted_proxy_count", 0)


class TestCompatibilityWithPythonJose:
    @pytest.mark.asyncio
    async def test_a_token_minted_by_python_jose_still_authenticates(self):
        session = _Session()
        user = await auth.get_current_user(session, _bearer(_JOSE_LIVE))
        assert user.id == 42 and session.lookups == [42]

    def test_the_token_minted_today_is_the_string_python_jose_minted(self, monkeypatch):
        # Pin "now" so exp lands on the fixture's: same alg, same header, same claim order, same bytes.
        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime.fromtimestamp(_FAR_EXP, tz=UTC)

        monkeypatch.setattr(auth_service, "datetime", _Frozen)
        monkeypatch.setattr(auth_service.settings, "jwt_expire_minutes", 0)
        minted = auth_service.create_access_token(User(id=42, email="compat@example.com", name="x", password_hash="h", session_epoch=3))
        assert minted == _JOSE_LIVE


class TestRefusals:
    @pytest.mark.parametrize("case", list(_REFUSED))
    @pytest.mark.asyncio
    async def test_the_jwt_dependency_answers_401_and_never_loads_a_user(self, case):
        session = _Session()
        with pytest.raises(CodedHTTPException) as refused:
            await auth.get_current_user(session, _bearer(_REFUSED[case]()))
        assert (refused.value.status_code, refused.value.code) == (401, "invalid_auth_token")
        assert session.lookups == []

    @pytest.mark.parametrize("case", list(_REFUSED))
    @pytest.mark.asyncio
    async def test_the_jwt_or_api_key_dependency_falls_through_to_the_key_and_answers_401(self, case, monkeypatch):
        tried: list[str] = []

        async def no_key(_session, raw_key: str):
            tried.append(raw_key)
            return None

        monkeypatch.setattr(api_key_service, "verify_api_key", no_key)
        token = _REFUSED[case]()
        session = _Session()
        with pytest.raises(CodedHTTPException) as refused:
            await api_key_auth.get_jwt_or_api_key_user(session, object(), _bearer(token))
        assert (refused.value.status_code, refused.value.code) == (401, "invalid_auth_token")
        # The JWT branch refused it (no user loaded) and the key branch was the one that answered.
        assert session.lookups == [] and tried == [token]

    @pytest.mark.parametrize("case", [c for c in _REFUSED if c not in ("no session_epoch", "non-numeric sub")])
    def test_the_rate_limit_falls_back_to_the_client_ip(self, case):
        # The limiter only needs a VERIFIED identity, not a complete one, so the two claim-shape cases the
        # dependencies refuse after decoding are not refusals here.
        assert rate_limit_key(_request(_REFUSED[case]())) == "ip:203.0.113.7"

    def test_the_rate_limit_keys_a_valid_token_by_its_user(self):
        assert rate_limit_key(_request(_JOSE_LIVE)) == "user:42"

    @pytest.mark.asyncio
    async def test_the_jwt_or_api_key_dependency_accepts_a_valid_token_without_trying_a_key(self, monkeypatch):
        async def must_not_run(*_args):
            raise AssertionError("a valid JWT must not reach the API-key lookup")

        monkeypatch.setattr(api_key_service, "verify_api_key", must_not_run)
        user = await api_key_auth.get_jwt_or_api_key_user(_Session(), object(), _bearer(_JOSE_LIVE))
        assert user.id == 42
