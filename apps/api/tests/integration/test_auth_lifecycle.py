import os
from datetime import date

import bcrypt
import httpx
import jwt
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

# The authentication lifecycle, driven through the real app with nothing but its database swapped.
#
# Every endpoint test in the unit suite overrides `get_current_user`, so the dependency that decides
# whether a token is still good never ran anywhere: deleting its session-epoch check — the line that makes
# "log out" (and a password change or reset) end every session — left the whole suite green. Here it runs
# for real, as the request role under row-level security, which is also what proves it sets the RLS user
# BEFORE reading the user: the users policy hides the row otherwise, and every valid token would 401.
#
# Two refusals that appeared in no test file at all ride along, each next to the near miss that must
# still succeed: login for an address that was never verified, and moving an account's opening date once
# money is linked to it.
#
# Two roles, as production runs them: the request session is `renly_app` (RLS_TEST_DATABASE_URL), the
# pre-auth and privileged sessions are `renly_admin` (RLS_TEST_ADMIN_DATABASE_URL), which also seeds.
from app.config import settings
from app.db import get_admin_session, get_auth_session, get_session
from app.main import create_app
from app.models.user import User
from app.rate_limit import limiter
from app.services import auth_service

APP_URL = os.getenv("RLS_TEST_DATABASE_URL")
ADMIN_URL = os.getenv("RLS_TEST_ADMIN_DATABASE_URL")

pytestmark = pytest.mark.skipif(
    not APP_URL or not ADMIN_URL,
    reason="set RLS_TEST_DATABASE_URL + RLS_TEST_ADMIN_DATABASE_URL (a real Postgres with the RLS schema) to run these",
)

_PREFIX = "u25auth_"
_PASSWORD = "correct horse battery staple"
_PASSWORD_HASH = bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt(rounds=4)).decode()


# The app with its three session dependencies bound to the two test roles, plus the admin factory for
# seeding and reading back. Nothing else is overridden — in particular not the user resolver.
@pytest_asyncio.fixture
async def env():
    app_engine = create_async_engine(APP_URL)
    admin_engine = create_async_engine(ADMIN_URL)
    app_factory = sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)
    admin_factory = sessionmaker(admin_engine, class_=AsyncSession, expire_on_commit=False)
    async with admin_factory() as s:
        await _cleanup(s)
        await s.commit()

    async def request_session():
        async with app_factory() as session:
            yield session

    async def privileged_session():
        async with admin_factory() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_session] = request_session
    app.dependency_overrides[get_auth_session] = privileged_session
    app.dependency_overrides[get_admin_session] = privileged_session
    limiter.reset()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, admin_factory
    limiter.reset()
    async with admin_factory() as s:
        await _cleanup(s)
        await s.commit()
    await app_engine.dispose()
    await admin_engine.dispose()


# Every user this file created, with their rows on the cascade.
async def _cleanup(s: AsyncSession) -> None:
    await s.execute(text("DELETE FROM users WHERE email LIKE :p"), {"p": f"{_PREFIX}%"})


# A user with a known password, verified unless told otherwise. Returns (id, email).
async def _user(admin_factory, tag: str, *, verified: bool = True) -> tuple[int, str]:
    email = f"{_PREFIX}{tag}@example.com"
    async with admin_factory() as s:
        user_id = (
            await s.execute(
                text(
                    "INSERT INTO users (name, email, password_hash, email_verified_at) VALUES (:n, :e, :h, CASE WHEN :v THEN NOW() END) RETURNING id"
                ),
                {"n": tag, "e": email, "h": _PASSWORD_HASH, "v": verified},
            )
        ).scalar_one()
        await s.commit()
    return user_id, email


# Logs in through the real endpoint.
async def _login(client: httpx.AsyncClient, email: str) -> httpx.Response:
    return await client.post("/auth/login", json={"email": email, "password": _PASSWORD})


# The Authorization header for an access token.
def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class TestLogoutEndsEverySession:
    @pytest.mark.asyncio
    async def test_a_token_issued_before_logout_is_refused_and_a_new_login_works(self, env):
        client, admin_factory = env
        user_id, email = await _user(admin_factory, "logout")
        # Two sessions, as two devices hold them.
        phone = (await _login(client, email)).json()["access_token"]
        laptop = (await _login(client, email)).json()["access_token"]

        me = await client.get("/auth/me", headers=_bearer(phone))
        assert me.status_code == 200 and me.json()["uid"] == user_id

        assert (await client.post("/auth/logout", headers=_bearer(phone))).status_code == 204

        # Logging out on one device ends the other too: both tokens carry the epoch before the bump.
        for token in (phone, laptop):
            refused = await client.get("/auth/me", headers=_bearer(token))
            assert refused.status_code == 401
            assert refused.json()["code"] == "invalid_auth_token"

        fresh = (await _login(client, email)).json()["access_token"]
        assert (await client.get("/auth/me", headers=_bearer(fresh))).status_code == 200

    @pytest.mark.asyncio
    async def test_a_token_whose_epoch_differs_either_way_is_refused(self, env):
        # Not only an older epoch: a token claiming any epoch the row does not hold is not one this
        # server issued for the account's current session.
        client, admin_factory = env
        user_id, email = await _user(admin_factory, "epoch")
        async with admin_factory() as s:
            await s.execute(text("UPDATE users SET session_epoch = 3 WHERE id = :u"), {"u": user_id})
            await s.commit()
        for epoch, status in ((3, 200), (2, 401), (4, 401)):
            token = auth_service.create_access_token(User(id=user_id, email=email, name="x", password_hash="h", session_epoch=epoch))
            assert (await client.get("/auth/me", headers=_bearer(token))).status_code == status, epoch

    @pytest.mark.asyncio
    async def test_a_token_naming_no_user_or_no_epoch_is_refused(self, env):
        client, admin_factory = env
        user_id, email = await _user(admin_factory, "ghost")
        # A well-signed token for an id with no row.
        ghost = auth_service.create_access_token(User(id=user_id + 10_000_000, email=email, name="x", password_hash="h", session_epoch=0))
        assert (await client.get("/auth/me", headers=_bearer(ghost))).status_code == 401
        # A well-signed token without the epoch claim at all.
        no_epoch = jwt.encode({"sub": str(user_id), "email": email}, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        assert (await client.get("/auth/me", headers=_bearer(no_epoch))).status_code == 401
        # And a token signed with some other key.
        forged = jwt.encode({"sub": str(user_id), "session_epoch": 0}, "not-the-secret-" * 3, algorithm=settings.jwt_algorithm)
        assert (await client.get("/auth/me", headers=_bearer(forged))).status_code == 401


class TestLoginRequiresAVerifiedAddress:
    @pytest.mark.asyncio
    async def test_an_unverified_address_is_refused_with_its_own_code_and_a_verified_one_logs_in(self, env):
        client, admin_factory = env
        _, unverified = await _user(admin_factory, "unverified", verified=False)
        refused = await _login(client, unverified)
        assert refused.status_code == 403
        assert refused.json()["code"] == "email_not_verified"
        assert "access_token" not in refused.json()

        _, verified = await _user(admin_factory, "verified")
        assert (await _login(client, verified)).status_code == 200


class TestAnAccountsOpeningDateLocksOnceMoneyIsLinked:
    @pytest.mark.asyncio
    async def test_moving_the_date_is_refused_with_a_link_and_allowed_without_one(self, env):
        client, admin_factory = env
        user_id, email = await _user(admin_factory, "accounts")
        async with admin_factory() as s:
            accounts = {}
            for name in ("linked", "bare"):
                accounts[name] = (
                    await s.execute(
                        text(
                            "INSERT INTO accounts (user_id, created_by, name, type, currency, opening_balance, opening_date) "
                            "VALUES (:u, :u, :n, 'bank', 'USD', 100, '2026-01-01') RETURNING id"
                        ),
                        {"u": user_id, "n": f"{_PREFIX}{name}"},
                    )
                ).scalar_one()
            await s.execute(
                text("INSERT INTO income_entries (user_id, date, amount, currency, account_id) VALUES (:u, '2026-01-05', 50, 'USD', :a)"),
                {"u": user_id, "a": accounts["linked"]},
            )
            await s.commit()
        token = (await _login(client, email)).json()["access_token"]

        refused = await client.put(f"/accounts/{accounts['linked']}", json={"opening_date": "2026-01-10"}, headers=_bearer(token))
        assert refused.status_code == 409
        assert refused.json()["code"] == "account_opening_date_change_blocked"
        # The same date resent is no move, and an unlinked account moves freely.
        assert (await client.put(f"/accounts/{accounts['linked']}", json={"opening_date": "2026-01-01"}, headers=_bearer(token))).status_code == 200
        moved = await client.put(f"/accounts/{accounts['bare']}", json={"opening_date": "2026-01-10"}, headers=_bearer(token))
        assert moved.status_code == 200 and moved.json()["opening_date"] == "2026-01-10"

        async with admin_factory() as s:
            dates = dict((await s.execute(text("SELECT id, opening_date FROM accounts WHERE user_id = :u"), {"u": user_id})).all())
        assert dates == {accounts["linked"]: date(2026, 1, 1), accounts["bare"]: date(2026, 1, 10)}
