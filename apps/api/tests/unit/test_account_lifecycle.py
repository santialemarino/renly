import re
from datetime import timedelta

import pytest

from app.config import SignupMode, settings
from app.domain import InvalidCredentialsError, InvalidTokenError, PasswordBreachedError
from app.models.auth_token import AuthToken, AuthTokenType
from app.models.user import User
from app.models.utils import utcnow
from app.services import account_service, auth_service

# Coverage for the M2 account-lifecycle service flows: email verification (AUTH-1), password reset
# (AUTH-2), change password/email (AUTH-8), account deletion + export (AUTH-6), and the uniform
# anti-enumeration registration (AUTH-5). Repositories + the email provider are faked (no DB/network).

_PASSWORD = "a-sufficiently-long-password"
_NEW_PASSWORD = "another-long-enough-password"


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
        self.deleted: list[int] = []

    async def get_by_id(self, session, user_id):
        return self.users.get(user_id)

    async def get_by_email(self, session, email):
        email = email.lower()
        return next((u for u in self.users.values() if u.email == email), None)

    async def create(self, session, user):
        user.id = self._next_id
        self._next_id += 1
        self.users[user.id] = user
        return user

    async def save(self, session, user):
        self.users[user.id] = user

    async def delete(self, session, user):
        self.deleted.append(user.id)
        self.users.pop(user.id, None)


class FakeTokenRepo:
    def __init__(self) -> None:
        self.tokens: list[AuthToken] = []
        self._next_id = 1

    async def get_by_hash(self, session, token_hash):
        return next((t for t in self.tokens if t.token_hash == token_hash), None)

    async def create(self, session, token):
        token.id = self._next_id
        self._next_id += 1
        self.tokens.append(token)
        return token

    async def save(self, session, token):
        return None

    async def delete_unconsumed_by_user_type(self, session, user_id, token_type):
        self.tokens = [t for t in self.tokens if not (t.user_id == user_id and t.token_type == token_type and t.consumed_at is None)]


class FakeInviteRepo:
    def __init__(self, emails: list[str] | None = None) -> None:
        self.emails = {e.lower() for e in (emails or [])}
        self.deleted: list[str] = []
        self.sessions: list[object] = []

    async def delete_by_email(self, session, email):
        email = email.lower()
        self.sessions.append(session)
        self.deleted.append(email)
        self.emails.discard(email)


class FakeEmailService:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message) -> None:
        self.sent.append(message)


# Extracts the raw token from the link embedded in a sent email.
def _token_from(message) -> str:
    match = re.search(r"token=(\S+)", message.text)
    assert match, "no token in email"
    return match.group(1)


async def _not_breached(_plain: str) -> bool:
    return False


# Wires the fakes into both service modules and disables the HIBP network call by default.
@pytest.fixture
def wired(monkeypatch):
    users = FakeUserRepo()
    tokens = FakeTokenRepo()
    email = FakeEmailService()
    monkeypatch.setattr(auth_service, "user_repository", users)
    monkeypatch.setattr(auth_service, "auth_token_repository", tokens)
    monkeypatch.setattr(auth_service, "get_email_service", lambda: email)
    monkeypatch.setattr(auth_service, "is_password_breached", _not_breached)
    monkeypatch.setattr(account_service, "user_repository", users)
    monkeypatch.setattr(account_service, "invite_repository", FakeInviteRepo())
    # These flows cover open registration + the lifecycle; the invite-only gate is orthogonal and
    # has its own coverage (test_invites.py), so exercise registration in open mode here.
    monkeypatch.setattr(settings, "signup_mode", SignupMode.open)
    return users, tokens, email


# --- Registration anti-enumeration (AUTH-5) ---


class TestRegisterAccount:
    @pytest.mark.asyncio
    async def test_new_email_creates_unverified_user_and_sends_verification(self, wired):
        users, tokens, email = wired
        await auth_service.register_account(FakeSession(), "Santi", "new@example.com", _PASSWORD)

        user = await users.get_by_email(None, "new@example.com")
        assert user is not None and user.email_verified_at is None
        assert len(tokens.tokens) == 1 and tokens.tokens[0].token_type == AuthTokenType.email_verification
        assert email.sent[0].to == "new@example.com"

    @pytest.mark.asyncio
    async def test_existing_email_creates_no_user_and_sends_account_exists(self, wired):
        users, tokens, email = wired
        await users.create(None, User(name="Santi", email="taken@example.com", password_hash="h"))

        await auth_service.register_account(FakeSession(), "Santi", "taken@example.com", _PASSWORD)

        assert len(users.users) == 1  # no second account created
        assert tokens.tokens == []  # no verification token issued
        assert email.sent[0].to == "taken@example.com"
        assert "token=" not in email.sent[0].text  # the notice carries no live link

    @pytest.mark.asyncio
    async def test_breached_password_is_rejected_before_branching(self, wired, monkeypatch):
        monkeypatch.setattr(auth_service, "is_password_breached", lambda _p: _breached())
        with pytest.raises(PasswordBreachedError):
            await auth_service.register_account(FakeSession(), "Santi", "new@example.com", _PASSWORD)


async def _breached() -> bool:
    return True


# --- Email verification (AUTH-1) ---


class TestEmailVerification:
    @pytest.mark.asyncio
    async def test_confirm_marks_user_verified(self, wired):
        users, tokens, email = wired
        await auth_service.register_account(FakeSession(), "Santi", "new@example.com", _PASSWORD)
        raw = _token_from(email.sent[0])

        token_type = await auth_service.confirm_email_token(FakeSession(), raw)

        assert token_type == AuthTokenType.email_verification
        user = await users.get_by_email(None, "new@example.com")
        assert user.email_verified_at is not None

    @pytest.mark.asyncio
    async def test_token_is_single_use(self, wired):
        _users, _tokens, email = wired
        await auth_service.register_account(FakeSession(), "Santi", "new@example.com", _PASSWORD)
        raw = _token_from(email.sent[0])
        await auth_service.confirm_email_token(FakeSession(), raw)

        with pytest.raises(InvalidTokenError):
            await auth_service.confirm_email_token(FakeSession(), raw)

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self, wired):
        users, tokens, _email = wired
        user = await users.create(None, User(name="S", email="u@example.com", password_hash="h"))
        raw = await auth_service.issue_token(FakeSession(), user.id, AuthTokenType.email_verification, timedelta(hours=24))
        # Force the just-issued token to be already expired.
        tokens.tokens[0].expires_at = utcnow() - timedelta(seconds=1)

        with pytest.raises(InvalidTokenError):
            await auth_service.confirm_email_token(FakeSession(), raw)

    @pytest.mark.asyncio
    async def test_request_verification_is_noop_for_verified_user(self, wired):
        users, tokens, email = wired
        await users.create(None, User(name="S", email="v@example.com", password_hash="h", email_verified_at=utcnow()))

        await auth_service.request_verification_email(FakeSession(), "v@example.com")

        assert tokens.tokens == [] and email.sent == []

    @pytest.mark.asyncio
    async def test_request_verification_is_noop_for_unknown_email(self, wired):
        _users, tokens, email = wired
        await auth_service.request_verification_email(FakeSession(), "ghost@example.com")
        assert tokens.tokens == [] and email.sent == []


# --- Password reset (AUTH-2) ---


class TestPasswordReset:
    @pytest.mark.asyncio
    async def test_reset_changes_hash_and_bumps_epoch(self, wired):
        users, _tokens, email = wired
        user = await users.create(None, User(name="S", email="r@example.com", password_hash=auth_service.hash_password(_PASSWORD), session_epoch=3))
        await auth_service.request_password_reset(FakeSession(), "r@example.com")
        raw = _token_from(email.sent[0])

        await auth_service.reset_password(FakeSession(), raw, _NEW_PASSWORD)

        assert auth_service.verify_password(_NEW_PASSWORD, user.password_hash)
        assert user.session_epoch == 4  # existing sessions invalidated

    @pytest.mark.asyncio
    async def test_forgot_password_is_noop_for_unknown_email(self, wired):
        _users, tokens, email = wired
        await auth_service.request_password_reset(FakeSession(), "ghost@example.com")
        assert tokens.tokens == [] and email.sent == []

    @pytest.mark.asyncio
    async def test_reset_with_invalid_token_rejected(self, wired):
        with pytest.raises(InvalidTokenError):
            await auth_service.reset_password(FakeSession(), "not-a-real-token", _NEW_PASSWORD)

    @pytest.mark.asyncio
    async def test_reset_token_type_is_enforced(self, wired):
        # A verification token must not be usable on the reset endpoint.
        users, _tokens, email = wired
        await auth_service.register_account(FakeSession(), "S", "x@example.com", _PASSWORD)
        verification_raw = _token_from(email.sent[0])
        with pytest.raises(InvalidTokenError):
            await auth_service.reset_password(FakeSession(), verification_raw, _NEW_PASSWORD)

    @pytest.mark.asyncio
    async def test_reissuing_a_reset_link_invalidates_the_previous_one(self, wired):
        # Requesting a second reset link must invalidate the first (only the latest works); merely
        # loading the reset page does not consume the token (no API call on page load).
        users, _tokens, email = wired
        await users.create(None, User(name="S", email="r@example.com", password_hash=auth_service.hash_password(_PASSWORD)))
        await auth_service.request_password_reset(FakeSession(), "r@example.com")
        first_raw = _token_from(email.sent[0])
        await auth_service.request_password_reset(FakeSession(), "r@example.com")
        second_raw = _token_from(email.sent[1])

        # The first (superseded) link no longer works...
        with pytest.raises(InvalidTokenError):
            await auth_service.reset_password(FakeSession(), first_raw, _NEW_PASSWORD)
        # ...the latest one does, and is then single-use.
        await auth_service.reset_password(FakeSession(), second_raw, _NEW_PASSWORD)
        with pytest.raises(InvalidTokenError):
            await auth_service.reset_password(FakeSession(), second_raw, _NEW_PASSWORD)


# --- Change email (AUTH-8) ---


class TestChangeEmail:
    @pytest.mark.asyncio
    async def test_change_email_to_free_address_sends_confirmation(self, wired):
        users, tokens, email = wired
        user = await users.create(None, User(name="S", email="old@example.com", password_hash=auth_service.hash_password(_PASSWORD)))

        await account_service.change_email(FakeSession(), user, _PASSWORD, "fresh@example.com")

        assert email.sent[0].to == "fresh@example.com"
        token = tokens.tokens[0]
        assert token.token_type == AuthTokenType.email_change and token.new_email == "fresh@example.com"
        # The address only switches on confirm — not yet.
        assert user.email == "old@example.com"

    @pytest.mark.asyncio
    async def test_confirm_email_change_switches_address_and_bumps_epoch(self, wired):
        users, _tokens, email = wired
        user = await users.create(
            None,
            User(
                name="S",
                email="old@example.com",
                password_hash=auth_service.hash_password(_PASSWORD),
                email_verified_at=utcnow(),
                session_epoch=1,
            ),
        )
        await account_service.change_email(FakeSession(), user, _PASSWORD, "fresh@example.com")
        raw = _token_from(email.sent[0])

        token_type = await auth_service.confirm_email_token(FakeSession(), raw)

        assert token_type == AuthTokenType.email_change
        assert user.email == "fresh@example.com"
        assert user.session_epoch == 2

    @pytest.mark.asyncio
    async def test_change_email_to_taken_address_sends_notice_no_token(self, wired):
        users, tokens, email = wired
        await users.create(None, User(name="Other", email="taken@example.com", password_hash="h"))
        user = await users.create(None, User(name="S", email="old@example.com", password_hash=auth_service.hash_password(_PASSWORD)))

        await account_service.change_email(FakeSession(), user, _PASSWORD, "taken@example.com")

        assert tokens.tokens == []  # no change token issued for a taken address
        assert email.sent[0].to == "taken@example.com"
        assert "token=" not in email.sent[0].text

    @pytest.mark.asyncio
    async def test_change_email_wrong_password_rejected(self, wired):
        users, _tokens, _email = wired
        user = await users.create(None, User(name="S", email="old@example.com", password_hash=auth_service.hash_password(_PASSWORD)))
        with pytest.raises(InvalidCredentialsError):
            await account_service.change_email(FakeSession(), user, "wrong-password", "fresh@example.com")


# --- Change password (AUTH-8) ---


class TestChangePassword:
    @pytest.mark.asyncio
    async def test_change_password_updates_hash_and_bumps_epoch(self, wired):
        users, _tokens, _email = wired
        user = await users.create(None, User(name="S", email="u@example.com", password_hash=auth_service.hash_password(_PASSWORD), session_epoch=0))

        await account_service.change_password(FakeSession(), user, _PASSWORD, _NEW_PASSWORD)

        assert auth_service.verify_password(_NEW_PASSWORD, user.password_hash)
        assert user.session_epoch == 1

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_rejected(self, wired):
        users, _tokens, _email = wired
        user = await users.create(None, User(name="S", email="u@example.com", password_hash=auth_service.hash_password(_PASSWORD)))
        with pytest.raises(InvalidCredentialsError):
            await account_service.change_password(FakeSession(), user, "wrong-password", _NEW_PASSWORD)


# --- Account deletion (AUTH-6) ---


class TestDeleteAccount:
    @pytest.mark.asyncio
    async def test_delete_requires_matching_password_and_confirmation(self, wired):
        users, _tokens, _email = wired
        user = await users.create(None, User(name="S", email="u@example.com", password_hash=auth_service.hash_password(_PASSWORD)))

        await account_service.delete_account(FakeSession(), FakeSession(), user, _PASSWORD, "U@Example.com")

        assert user.id in users.deleted

    @pytest.mark.asyncio
    async def test_delete_wrong_password_rejected(self, wired):
        users, _tokens, _email = wired
        user = await users.create(None, User(name="S", email="u@example.com", password_hash=auth_service.hash_password(_PASSWORD)))
        with pytest.raises(InvalidCredentialsError):
            await account_service.delete_account(FakeSession(), FakeSession(), user, "wrong", "u@example.com")
        assert users.deleted == []

    @pytest.mark.asyncio
    async def test_delete_confirmation_must_match_email(self, wired):
        users, _tokens, _email = wired
        user = await users.create(None, User(name="S", email="u@example.com", password_hash=auth_service.hash_password(_PASSWORD)))
        with pytest.raises(InvalidCredentialsError):
            await account_service.delete_account(FakeSession(), FakeSession(), user, _PASSWORD, "not-the-email")
        assert users.deleted == []

    @pytest.mark.asyncio
    async def test_delete_clears_the_invite_that_created_the_account(self, wired, monkeypatch):
        users, _tokens, _email = wired
        invites = FakeInviteRepo(emails=["u@example.com"])
        monkeypatch.setattr(account_service, "invite_repository", invites)
        user = await users.create(None, User(name="S", email="u@example.com", password_hash=auth_service.hash_password(_PASSWORD)))
        request_session, admin_session = FakeSession(), FakeSession()

        await account_service.delete_account(request_session, admin_session, user, _PASSWORD, "u@example.com")

        assert user.id in users.deleted
        assert invites.deleted == ["u@example.com"]
        # The invite is keyed to the inviting admin, so it must be cleared on the privileged session
        # (RLS hides it from the user's own session) — never the request session.
        assert invites.sessions == [admin_session]


# --- Data export (AUTH-6) ---


class TestExport:
    @pytest.mark.asyncio
    async def test_export_excludes_secrets(self, wired, monkeypatch):
        async def fake_dump(session, user_id):
            return {"api_keys": [], "investments": []}

        monkeypatch.setattr(account_service.export_repository, "dump_user_data", fake_dump)
        user = User(id=7, name="S", email="u@example.com", password_hash="secret-hash")

        data = await account_service.export_user_data(FakeSession(), user)

        assert data["user"]["email"] == "u@example.com"
        assert "password_hash" not in data["user"]
        assert data["api_keys"] == []
        assert "investments" in data
