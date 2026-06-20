from datetime import timedelta

import pytest

from app.config import settings
from app.domain import InvalidRefreshTokenError
from app.models.refresh_token import RefreshToken
from app.models.user import User
from app.models.utils import utcnow
from app.services import refresh_token_service
from app.services.refresh_token_service import REUSE_GRACE

# Coverage for the AUTH-7 rotating refresh tokens: issue at login (remember vs ordinary window),
# single-use rotation, reuse-detection (family revocation outside the grace window), the grace window
# that tolerates NextAuth's benign parallel replays, and session_epoch / expiry / revocation
# invalidation. Repositories are faked (no DB).


# Fake session: the flows only need commit/flush to be awaitable no-ops (the fake repos hold state).
class FakeSession:
    async def commit(self) -> None:
        return None

    async def flush(self) -> None:
        return None


class FakeUserRepo:
    def __init__(self, users: list[User] | None = None) -> None:
        self.users = {u.id: u for u in (users or [])}
        self._next_id = (max(self.users) + 1) if self.users else 1

    async def get_by_id(self, session, user_id):
        return self.users.get(user_id)

    async def create(self, session, user):
        user.id = self._next_id
        self._next_id += 1
        self.users[user.id] = user
        return user


class FakeRefreshRepo:
    def __init__(self) -> None:
        self.tokens: list[RefreshToken] = []
        self._next_id = 1

    async def get_by_hash(self, session, token_hash):
        return next((t for t in self.tokens if t.token_hash == token_hash), None)

    async def create(self, session, token):
        token.id = self._next_id
        self._next_id += 1
        self.tokens.append(token)
        return token

    async def save(self, session, token):
        return None  # tokens are mutated in place; already held in the list

    async def revoke_family(self, session, family_id, revoked_at):
        for token in self.tokens:
            if token.family_id == family_id and token.revoked_at is None:
                token.revoked_at = revoked_at

    async def delete_expired_by_user(self, session, user_id, now):
        self.tokens = [t for t in self.tokens if not (t.user_id == user_id and t.expires_at < now)]


# Wires the fakes into the service and seeds one user. Returns (user, refresh_repo).
@pytest.fixture
def wired(monkeypatch):
    users = FakeUserRepo()
    tokens = FakeRefreshRepo()
    monkeypatch.setattr(refresh_token_service, "user_repository", users)
    monkeypatch.setattr(refresh_token_service, "refresh_token_repository", tokens)
    user = User(name="S", email="u@example.com", password_hash="h", session_epoch=0)
    users.users[1] = user
    user.id = 1
    return user, tokens


class TestIssue:
    @pytest.mark.asyncio
    async def test_remember_me_uses_the_long_window(self, wired):
        user, tokens = wired
        issued = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=True)

        assert issued.expires_in == settings.refresh_token_remember_days * 86400
        assert len(tokens.tokens) == 1
        token = tokens.tokens[0]
        assert token.remember_me is True and token.session_epoch == user.session_epoch
        assert token.consumed_at is None and token.revoked_at is None

    @pytest.mark.asyncio
    async def test_ordinary_login_uses_the_short_window(self, wired):
        user, _tokens = wired
        issued = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=False)
        assert issued.expires_in == settings.refresh_token_default_hours * 3600


class TestRotation:
    @pytest.mark.asyncio
    async def test_rotate_consumes_the_token_and_mints_a_successor(self, wired):
        user, tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=True)

        rotated_user, second = await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

        assert rotated_user.id == user.id
        assert second.raw_token != first.raw_token
        assert len(tokens.tokens) == 2
        assert tokens.tokens[0].consumed_at is not None  # the presented token is spent
        assert tokens.tokens[1].family_id == tokens.tokens[0].family_id  # successor stays in the family
        assert tokens.tokens[1].consumed_at is None

    @pytest.mark.asyncio
    async def test_successor_keeps_rotating(self, wired):
        user, _tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=False)
        _u, second = await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

        _u2, third = await refresh_token_service.rotate_refresh_token(FakeSession(), second.raw_token)
        assert third.raw_token not in (first.raw_token, second.raw_token)


class TestReuseDetection:
    @pytest.mark.asyncio
    async def test_reuse_outside_grace_revokes_the_whole_family(self, wired):
        user, tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=True)
        _u, second = await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

        # Age the consumed token past the grace window so re-presentation reads as theft.
        tokens.tokens[0].consumed_at = utcnow() - (REUSE_GRACE + timedelta(seconds=1))
        with pytest.raises(InvalidRefreshTokenError):
            await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

        # The whole family is revoked — even the legitimate successor no longer works.
        assert all(t.revoked_at is not None for t in tokens.tokens)
        with pytest.raises(InvalidRefreshTokenError):
            await refresh_token_service.rotate_refresh_token(FakeSession(), second.raw_token)

    @pytest.mark.asyncio
    async def test_replay_within_grace_is_tolerated(self, wired):
        user, tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=True)
        _u, second = await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

        # Re-presenting the just-consumed token (within grace) mints a fresh token without revoking.
        _u2, third = await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

        assert third.raw_token not in (first.raw_token, second.raw_token)
        assert all(t.revoked_at is None for t in tokens.tokens)


class TestInvalidation:
    @pytest.mark.asyncio
    async def test_session_epoch_bump_invalidates_the_token(self, wired):
        user, _tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=True)

        user.session_epoch += 1  # e.g. a logout / password change since the token was minted
        with pytest.raises(InvalidRefreshTokenError):
            await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, wired):
        user, tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=False)
        tokens.tokens[0].expires_at = utcnow() - timedelta(seconds=1)
        with pytest.raises(InvalidRefreshTokenError):
            await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

    @pytest.mark.asyncio
    async def test_revoked_token_rejected(self, wired):
        user, tokens = wired
        first = await refresh_token_service.issue_refresh_token(FakeSession(), user, remember_me=False)
        tokens.tokens[0].revoked_at = utcnow()
        with pytest.raises(InvalidRefreshTokenError):
            await refresh_token_service.rotate_refresh_token(FakeSession(), first.raw_token)

    @pytest.mark.asyncio
    async def test_unknown_token_rejected(self, wired):
        with pytest.raises(InvalidRefreshTokenError):
            await refresh_token_service.rotate_refresh_token(FakeSession(), "not-a-real-token")
