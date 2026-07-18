import re
from datetime import timedelta

import pytest
from fastapi import HTTPException

from app.config import SignupMode, settings
from app.deps.auth import get_admin_user
from app.domain import InvalidInviteError, InviteEmailTakenError, NotFoundError
from app.models.auth_token import AuthToken
from app.models.invite import Invite, InviteStatus
from app.models.user import User
from app.models.utils import utcnow
from app.services import auth_service, invite_service, settings_service

# Coverage for the invite-only access gate (go-live prerequisite): invite create / single-use consume
# / expiry / email-mismatch, resend + revoke, the SIGNUP_MODE gate on registration (invite requires a
# valid invite; open bypasses), the preserved uniform-202 anti-enumeration, and the AdminUser guard.
# Repositories + the email provider are faked (no DB / network).

_PASSWORD = "a-sufficiently-long-password"


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


class FakeInviteRepo:
    def __init__(self) -> None:
        self.invites: dict[int, Invite] = {}
        self._next_id = 1

    async def list_all(self, session):
        return sorted(self.invites.values(), key=lambda i: i.created_at, reverse=True)

    async def get_by_id(self, session, invite_id):
        return self.invites.get(invite_id)

    async def get_by_email(self, session, email):
        email = email.lower()
        return next((i for i in self.invites.values() if i.email == email), None)

    async def get_by_hash(self, session, token_hash):
        return next((i for i in self.invites.values() if i.token_hash == token_hash), None)

    async def create(self, session, invite):
        if invite.id is None:
            invite.id = self._next_id
            self._next_id += 1
        self.invites[invite.id] = invite
        return invite

    async def save(self, session, invite):
        self.invites[invite.id] = invite


class FakeAuthTokenRepo:
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


class FakeEmailService:
    def __init__(self) -> None:
        self.sent = []

    async def send(self, message) -> None:
        self.sent.append(message)


# Extracts the raw invite token from the signup link embedded in a sent invite email.
def _invite_token_from(message) -> str:
    match = re.search(r"invite=(\S+)", message.text)
    assert match, "no invite token in email"
    return match.group(1)


async def _not_breached(_plain: str) -> bool:
    return False


# Wires the fakes into both invite_service and auth_service so the gate flows share one user store and
# email outbox, and forces SIGNUP_MODE=invite by default (each test overrides as needed).
@pytest.fixture
def wired(monkeypatch):
    users = FakeUserRepo()
    invites = FakeInviteRepo()
    auth_tokens = FakeAuthTokenRepo()
    email = FakeEmailService()
    monkeypatch.setattr(invite_service, "invite_repository", invites)
    monkeypatch.setattr(invite_service, "user_repository", users)
    monkeypatch.setattr(invite_service, "get_email_service", lambda: email)
    monkeypatch.setattr(auth_service, "user_repository", users)
    monkeypatch.setattr(auth_service, "auth_token_repository", auth_tokens)
    monkeypatch.setattr(auth_service, "get_email_service", lambda: email)
    monkeypatch.setattr(auth_service, "is_password_breached", _not_breached)
    # The invite emails resolve the inviting admin's language; stub it off the FakeSession.
    monkeypatch.setattr(settings_service, "get_user_language", _stub_get_language)
    monkeypatch.setattr(settings, "signup_mode", SignupMode.invite)
    return users, invites, email


# Language stub so invite/register flows don't hit the real settings repo on the FakeSession.
async def _stub_get_language(_session, _user_id) -> str:
    return "en"


# --- Invite creation ---


class TestCreateInvite:
    @pytest.mark.asyncio
    async def test_create_stores_pending_invite_and_emails_link(self, wired):
        _users, invites, email = wired
        invite = await invite_service.create_invite(FakeSession(), "Friend@Example.com", invited_by_id=7)

        assert invite.email == "friend@example.com"  # lowercased
        assert invite.status == InviteStatus.pending and invite.invited_by == 7
        assert len(invites.invites) == 1
        assert email.sent[0].to == "friend@example.com" and "invite=" in email.sent[0].text

    @pytest.mark.asyncio
    async def test_create_rejects_an_email_that_already_has_an_account(self, wired):
        users, _invites, _email = wired
        await users.create(None, User(name="U", email="taken@example.com", password_hash="h"))
        with pytest.raises(InviteEmailTakenError):
            await invite_service.create_invite(FakeSession(), "taken@example.com", invited_by_id=1)

    @pytest.mark.asyncio
    async def test_reinviting_the_same_email_rotates_the_token(self, wired):
        _users, invites, email = wired
        await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        first_token = _invite_token_from(email.sent[0])
        await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)

        assert len(invites.invites) == 1  # one invite per email, rotated in place
        # The first (superseded) link no longer resolves; the latest one does.
        assert await invite_service.get_pending_invite_by_token(FakeSession(), first_token) is None
        assert await invite_service.get_pending_invite_by_token(FakeSession(), _invite_token_from(email.sent[1])) is not None

    @pytest.mark.asyncio
    async def test_reinviting_a_revoked_email_rearms_it(self, wired):
        _users, invites, email = wired
        created = await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        await invite_service.revoke_invite(FakeSession(), created.id)

        rearmed = await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)

        assert rearmed.id == created.id  # same row re-armed in place, not duplicated
        assert rearmed.status == InviteStatus.pending and len(invites.invites) == 1
        # The fresh link resolves again (the revoked state no longer blocks it).
        assert await invite_service.get_valid_invite(FakeSession(), _invite_token_from(email.sent[-1]), "f@example.com") is not None


# --- Validation + single-use consume (registration path) ---


class TestInviteValidation:
    @pytest.mark.asyncio
    async def test_valid_token_with_matching_email_resolves(self, wired):
        _users, _invites, email = wired
        await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])

        invite = await invite_service.get_valid_invite(FakeSession(), raw, "f@example.com")
        assert invite.email == "f@example.com"

    @pytest.mark.asyncio
    async def test_email_mismatch_is_rejected(self, wired):
        _users, _invites, email = wired
        await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])
        with pytest.raises(InvalidInviteError):
            await invite_service.get_valid_invite(FakeSession(), raw, "someone-else@example.com")

    @pytest.mark.asyncio
    async def test_missing_token_is_rejected(self, wired):
        with pytest.raises(InvalidInviteError):
            await invite_service.get_valid_invite(FakeSession(), None, "f@example.com")

    @pytest.mark.asyncio
    async def test_expired_invite_is_rejected(self, wired):
        _users, invites, email = wired
        await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])
        next(iter(invites.invites.values())).expires_at = utcnow() - timedelta(seconds=1)
        with pytest.raises(InvalidInviteError):
            await invite_service.get_valid_invite(FakeSession(), raw, "f@example.com")

    @pytest.mark.asyncio
    async def test_consume_makes_the_invite_single_use(self, wired):
        _users, _invites, email = wired
        await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])
        invite = await invite_service.get_valid_invite(FakeSession(), raw, "f@example.com")

        await invite_service.consume_invite(FakeSession(), invite)

        assert invite.status == InviteStatus.accepted and invite.consumed_at is not None
        with pytest.raises(InvalidInviteError):  # the same link can't be reused
            await invite_service.get_valid_invite(FakeSession(), raw, "f@example.com")


# --- Resend + revoke ---


class TestResendRevoke:
    @pytest.mark.asyncio
    async def test_resend_rotates_the_token_and_kills_the_old_link(self, wired):
        _users, invites, email = wired
        created = await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        old_token = _invite_token_from(email.sent[0])

        await invite_service.resend_invite(FakeSession(), created.id)

        assert await invite_service.get_pending_invite_by_token(FakeSession(), old_token) is None
        assert await invite_service.get_pending_invite_by_token(FakeSession(), _invite_token_from(email.sent[1])) is not None

    @pytest.mark.asyncio
    async def test_revoke_invalidates_the_invite(self, wired):
        _users, _invites, email = wired
        created = await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])

        revoked = await invite_service.revoke_invite(FakeSession(), created.id)

        assert revoked.status == InviteStatus.revoked
        with pytest.raises(InvalidInviteError):
            await invite_service.get_valid_invite(FakeSession(), raw, "f@example.com")

    @pytest.mark.asyncio
    async def test_resend_rearms_a_revoked_invite(self, wired):
        _users, _invites, email = wired
        created = await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        await invite_service.revoke_invite(FakeSession(), created.id)

        resent = await invite_service.resend_invite(FakeSession(), created.id)

        assert resent.status == InviteStatus.pending  # revoked → resend re-arms it
        assert await invite_service.get_valid_invite(FakeSession(), _invite_token_from(email.sent[-1]), "f@example.com") is not None

    @pytest.mark.asyncio
    async def test_resend_and_revoke_reject_an_accepted_invite(self, wired):
        _users, _invites, email = wired
        created = await invite_service.create_invite(FakeSession(), "f@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])
        await invite_service.consume_invite(FakeSession(), await invite_service.get_valid_invite(FakeSession(), raw, "f@example.com"))

        with pytest.raises(InviteEmailTakenError):
            await invite_service.resend_invite(FakeSession(), created.id)
        with pytest.raises(InviteEmailTakenError):
            await invite_service.revoke_invite(FakeSession(), created.id)

    @pytest.mark.asyncio
    async def test_resend_and_revoke_unknown_id_raise_not_found(self, wired):
        with pytest.raises(NotFoundError):
            await invite_service.resend_invite(FakeSession(), 999)
        with pytest.raises(NotFoundError):
            await invite_service.revoke_invite(FakeSession(), 999)


# --- Effective status (admin list) ---


class TestEffectiveStatus:
    def test_pending_past_expiry_reads_as_expired(self):
        invite = Invite(email="f@example.com", token_hash="h", invited_by=1, status=InviteStatus.pending, expires_at=utcnow() - timedelta(days=1))
        assert invite_service.effective_status(invite) == "expired"

    def test_stored_statuses_pass_through(self):
        future = utcnow() + timedelta(days=1)
        assert (
            invite_service.effective_status(Invite(email="a@x.com", token_hash="h", invited_by=1, status=InviteStatus.pending, expires_at=future))
            == "pending"
        )
        assert (
            invite_service.effective_status(Invite(email="b@x.com", token_hash="h", invited_by=1, status=InviteStatus.accepted, expires_at=future))
            == "accepted"
        )
        assert (
            invite_service.effective_status(Invite(email="c@x.com", token_hash="h", invited_by=1, status=InviteStatus.revoked, expires_at=future))
            == "revoked"
        )


# --- SIGNUP_MODE gate on registration ---


class TestRegisterGate:
    @pytest.mark.asyncio
    async def test_invite_mode_without_a_token_is_rejected(self, wired):
        users, _invites, _email = wired
        with pytest.raises(InvalidInviteError):
            await auth_service.register_account(FakeSession(), "S", "new@example.com", _PASSWORD, invite_token=None)
        assert users.users == {}  # no account created

    @pytest.mark.asyncio
    async def test_invite_mode_with_a_valid_invite_creates_the_user_and_consumes_it(self, wired):
        users, invites, email = wired
        await invite_service.create_invite(FakeSession(), "new@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])

        await auth_service.register_account(FakeSession(), "S", "new@example.com", _PASSWORD, invite_token=raw)

        user = await users.get_by_email(None, "new@example.com")
        assert user is not None and user.email_verified_at is None
        assert next(iter(invites.invites.values())).status == InviteStatus.accepted  # consumed
        assert email.sent[-1].to == "new@example.com" and "token=" in email.sent[-1].text  # verification link

    @pytest.mark.asyncio
    async def test_invite_mode_email_mismatch_is_rejected(self, wired):
        users, _invites, email = wired
        await invite_service.create_invite(FakeSession(), "invited@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])
        with pytest.raises(InvalidInviteError):
            await auth_service.register_account(FakeSession(), "S", "attacker@example.com", _PASSWORD, invite_token=raw)
        assert await users.get_by_email(None, "attacker@example.com") is None

    @pytest.mark.asyncio
    async def test_a_consumed_invite_cannot_be_reused_to_register(self, wired):
        _users, _invites, email = wired
        await invite_service.create_invite(FakeSession(), "new@example.com", invited_by_id=1)
        raw = _invite_token_from(email.sent[0])
        await auth_service.register_account(FakeSession(), "S", "new@example.com", _PASSWORD, invite_token=raw)

        with pytest.raises(InvalidInviteError):
            await auth_service.register_account(FakeSession(), "S", "new@example.com", _PASSWORD, invite_token=raw)

    @pytest.mark.asyncio
    async def test_uniform_202_preserved_for_an_already_registered_invited_email(self, wired):
        # A valid invite whose email already has an account: no second user, the invite is consumed,
        # and the "account exists" notice (no live link) is sent — the same outcome shape as a new
        # signup, so registration still never reveals whether the address is taken (AUTH-5).
        users, invites, email = wired
        await users.create(None, User(name="Existing", email="dup@example.com", password_hash="h"))
        # Seed the invite directly (create_invite refuses an address that already has an account).
        invite = await invites.create(
            None,
            Invite(
                email="dup@example.com",
                token_hash=invite_service._hash_token("rawdup"),
                invited_by=1,
                status=InviteStatus.pending,
                expires_at=utcnow() + timedelta(days=1),
            ),
        )

        await auth_service.register_account(FakeSession(), "S", "dup@example.com", _PASSWORD, invite_token="rawdup")

        assert len(users.users) == 1  # no second account
        assert invite.status == InviteStatus.accepted  # invite still consumed
        assert email.sent[-1].to == "dup@example.com" and "token=" not in email.sent[-1].text  # notice, no link

    @pytest.mark.asyncio
    async def test_open_mode_bypasses_the_invite_gate(self, wired, monkeypatch):
        users, _invites, email = wired
        monkeypatch.setattr(settings, "signup_mode", SignupMode.open)

        await auth_service.register_account(FakeSession(), "S", "open@example.com", _PASSWORD, invite_token=None)

        user = await users.get_by_email(None, "open@example.com")
        assert user is not None and user.email_verified_at is None
        assert email.sent[-1].to == "open@example.com" and "token=" in email.sent[-1].text

    @pytest.mark.asyncio
    async def test_consumed_invite_is_independent_of_the_user_row(self, wired):
        # The invite binds to (email, inviting admin), never the registered user's row: it has no FK
        # to users.id (only invited_by, the admin). So an account email/password change can't touch
        # it — after registration consumes it, it stays bound to the original address + admin.
        users, invites, email = wired
        await invite_service.create_invite(FakeSession(), "new@example.com", invited_by_id=9)
        raw = _invite_token_from(email.sent[0])
        await auth_service.register_account(FakeSession(), "S", "new@example.com", _PASSWORD, invite_token=raw)

        invite = next(iter(invites.invites.values()))
        user = await users.get_by_email(None, "new@example.com")
        assert invite.status == InviteStatus.accepted
        assert not hasattr(invite, "user_id")  # no link back to the registered account

        # Simulate the user later changing their email — the consumed invite is untouched.
        user.email = "changed@example.com"
        await users.save(None, user)
        assert invite.email == "new@example.com" and invite.invited_by == 9


# --- Admin authorization guard ---


class TestAdminUserDependency:
    @pytest.mark.asyncio
    async def test_non_admin_is_forbidden(self):
        user = User(id=1, name="S", email="u@example.com", password_hash="h", is_admin=False)
        with pytest.raises(HTTPException) as exc:
            await get_admin_user(user)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_passes_through(self):
        user = User(id=1, name="S", email="a@example.com", password_hash="h", is_admin=True)
        assert await get_admin_user(user) is user
