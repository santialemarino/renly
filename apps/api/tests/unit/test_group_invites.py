# Unit coverage for the group-seat invite service: the token mechanism (only the hash is stored, the
# raw value appears once, rotation kills the previous link), the single answer every unusable token
# gets, what the pre-membership preview may and may not disclose, and the accept path's guards.
#
# The token is the credential — a group invite links an existing account to a seat and creates nothing —
# so there is no email-match assertion to make here, deliberately. What IS asserted is everything that
# bounds a link: single-use, expiry, revocability, and rotation on resend.

import hashlib
from datetime import timedelta
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest

from app.config import settings
from app.domain import GroupAdminRequiredError, GroupMembershipExistsError, GroupSeatTakenError, InvalidTokenError, NotFoundError
from app.models.group import Group, GroupKind, GroupMember, GroupMemberRole
from app.models.group_invite import GroupInvite
from app.models.user import User
from app.models.utils import utcnow
from app.services import group_invite_service

ADMIN = User(id=1, name="Santi", email="admin@test", password_hash="x", session_epoch=0)
JOINER = User(id=2, name="Ana", email="ana@test", password_hash="x", session_epoch=0)

_GROUP_ID = 10
_MEMBER_ID = 3


def _group() -> Group:
    return Group(id=_GROUP_ID, name="Casa", kind=GroupKind.household, created_by=ADMIN.id)


def _seat(*, user_id: int | None = None, is_active: bool = True) -> GroupMember:
    return GroupMember(id=_MEMBER_ID, group_id=_GROUP_ID, user_id=user_id, display_name="Ana", is_active=is_active)


def _invite(*, consumed: bool = False, expired: bool = False, email: str | None = None) -> GroupInvite:
    now = utcnow()
    return GroupInvite(
        id=99,
        group_id=_GROUP_ID,
        member_id=_MEMBER_ID,
        email=email,
        token_hash="old-hash",
        expires_at=now - timedelta(seconds=1) if expired else now + timedelta(days=7),
        consumed_at=now if consumed else None,
        created_by=ADMIN.id,
    )


# Stands in for group_service.require_admin, whose own gate is covered in test_group_service.py.
def _allow_admin(monkeypatch, group: Group | None = None):
    seat = GroupMember(id=1, group_id=_GROUP_ID, user_id=ADMIN.id, display_name="Santi", role=GroupMemberRole.admin)
    monkeypatch.setattr(group_invite_service.group_service, "require_admin", AsyncMock(return_value=(group or _group(), seat)))


def _patch_group_repo(monkeypatch, **methods):
    for name in ("get_by_id", "get_member", "get_member_by_user", "save_member"):
        monkeypatch.setattr(group_invite_service.group_repository, name, methods.get(name, AsyncMock()))


def _patch_invite_repo(monkeypatch, **methods):
    for name in ("create", "delete_by_member", "get_by_hash", "get_by_member", "save"):
        monkeypatch.setattr(group_invite_service.group_invite_repository, name, methods.get(name, AsyncMock(return_value=None)))


# Neutralises the outbound email and the language lookup for tests that are not about them.
def _patch_delivery(monkeypatch, send: AsyncMock | None = None):
    monkeypatch.setattr(group_invite_service, "_safe_send", send or AsyncMock())
    monkeypatch.setattr(group_invite_service.settings_service, "get_user_language", AsyncMock(return_value="en"))
    monkeypatch.setattr(group_invite_service.user_repository, "get_by_id", AsyncMock(return_value=ADMIN))


class TestAdminGate:
    # Every other test here stubs require_admin so it succeeds, which is exactly what hid this: with
    # the stub in place, a service that stopped calling the gate at all still passed. These two let the
    # real gate run and assert a plain member is refused.
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "call",
        [
            pytest.param(lambda s: group_invite_service.create_invite(s, _GROUP_ID, _MEMBER_ID, JOINER), id="create_invite"),
            pytest.param(lambda s: group_invite_service.revoke_invite(s, _GROUP_ID, _MEMBER_ID, JOINER), id="revoke_invite"),
        ],
    )
    async def test_a_plain_member_cannot_manage_invites(self, monkeypatch, call):
        seat = GroupMember(id=2, group_id=_GROUP_ID, user_id=JOINER.id, display_name="Ana", role=GroupMemberRole.member)
        monkeypatch.setattr(
            group_invite_service.group_service.group_repository,
            "get_by_id",
            AsyncMock(return_value=_group()),
        )
        monkeypatch.setattr(
            group_invite_service.group_service.group_repository,
            "get_member_by_user",
            AsyncMock(return_value=seat),
        )
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch)
        _patch_delivery(monkeypatch)
        with pytest.raises(GroupAdminRequiredError):
            await call(AsyncMock())


class TestCreateInvite:
    @pytest.mark.asyncio
    async def test_only_the_hash_is_stored_and_it_matches_the_link_that_is_returned(self, monkeypatch):
        created = AsyncMock(side_effect=lambda _s, invite: invite)
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, create=created)
        _patch_delivery(monkeypatch)

        response = await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)
        raw_token = response.invite_url.split("token=")[1]
        stored = created.await_args.args[1]
        assert stored.token_hash == hashlib.sha256(raw_token.encode()).hexdigest()
        # The raw token exists nowhere on the row — a DB leak cannot reconstruct a live link.
        assert raw_token not in (stored.token_hash, stored.email or "")

    @pytest.mark.asyncio
    async def test_the_link_points_at_the_public_join_page(self, monkeypatch):
        # It must be reachable logged out: most recipients open it without a session, and a protected
        # landing page would bounce them to login and drop the token.
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, create=AsyncMock(side_effect=lambda _s, invite: invite))
        _patch_delivery(monkeypatch)
        response = await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)
        parsed = urlparse(response.invite_url)
        # The exact path, not a substring: "/shared/join" contains "/join" and would be protected.
        assert parsed.path == "/join"
        assert parse_qs(parsed.query)["token"]
        # And it must be built from the configured web origin — a hardcoded host would send every
        # invite in production to the wrong place, silently.
        assert response.invite_url.startswith(settings.web_base_url)

    @pytest.mark.asyncio
    async def test_the_invite_records_who_sent_it(self, monkeypatch):
        # created_by is what the pre-membership preview resolves "X invited you" from, so losing it
        # makes every join page anonymous.
        created = AsyncMock(side_effect=lambda _s, invite: invite)
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, create=created)
        _patch_delivery(monkeypatch)
        await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)
        assert created.await_args.args[1].created_by == ADMIN.id

    @pytest.mark.asyncio
    async def test_omitting_the_email_sends_nothing_and_still_returns_a_link(self, monkeypatch):
        # The shareable-link half of the feature: the caller distributes it themselves.
        send = AsyncMock()
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, create=AsyncMock(side_effect=lambda _s, invite: invite))
        _patch_delivery(monkeypatch, send=send)
        response = await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN, email=None)
        assert response.email is None
        assert response.invite_url
        send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_an_email_invite_sends_the_link_with_the_group_and_inviter_named(self, monkeypatch):
        send = AsyncMock()
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, create=AsyncMock(side_effect=lambda _s, invite: invite))
        _patch_delivery(monkeypatch, send=send)
        response = await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN, email="Ana@Test.COM")
        assert send.await_count == 1
        message = send.await_args.args[0]
        assert message.to == "ana@test.com"
        assert "Casa" in message.subject and "Santi" in message.subject
        assert response.invite_url in message.text
        # Stored lowercased, so the address the roster shows matches what was sent.
        assert response.email == "ana@test.com"

    @pytest.mark.asyncio
    async def test_a_resend_rotates_the_token_in_place_so_the_previous_link_dies(self, monkeypatch):
        existing = _invite(email="old@test.com")
        old_hash = existing.token_hash
        old_expiry = existing.expires_at
        saved = AsyncMock()
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, get_by_member=AsyncMock(return_value=existing), save=saved, create=AsyncMock())
        _patch_delivery(monkeypatch)

        response = await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN, email="new@test.com")
        assert existing.token_hash != old_hash
        assert existing.expires_at > old_expiry
        assert existing.email == "new@test.com"
        assert response.invite_url.split("token=")[1]
        saved.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_resend_clears_a_stale_consumed_at(self, monkeypatch):
        # Rotating a consumed row must re-arm it, or a seat whose member later left could never be
        # re-invited (UNIQUE (member_id) means there is only ever this one row).
        existing = _invite(consumed=True)
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, get_by_member=AsyncMock(return_value=existing), save=AsyncMock())
        _patch_delivery(monkeypatch)
        await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)
        assert existing.consumed_at is None

    @pytest.mark.asyncio
    async def test_a_seat_someone_already_holds_cannot_be_invited(self, monkeypatch):
        # There would be nothing to claim, so the token could only ever fail. The error must be the
        # seat-taken one, NOT GroupMembershipExistsError — that one says "you are already a member of
        # this group", which is the wrong sentence to show an admin inviting somebody else.
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat(user_id=JOINER.id)))
        _patch_invite_repo(monkeypatch)
        _patch_delivery(monkeypatch)
        with pytest.raises(GroupSeatTakenError):
            await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)

    @pytest.mark.asyncio
    async def test_a_removed_seat_cannot_be_invited(self, monkeypatch):
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat(is_active=False)))
        _patch_invite_repo(monkeypatch)
        _patch_delivery(monkeypatch)
        with pytest.raises(NotFoundError):
            await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)

    @pytest.mark.asyncio
    async def test_a_send_failure_does_not_fail_the_request(self, monkeypatch):
        # The invite is already committed and the link is already in the response; an email outage
        # would otherwise lose a persisted invite the caller cannot see.
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, create=AsyncMock(side_effect=lambda _s, invite: invite))
        monkeypatch.setattr(group_invite_service.settings_service, "get_user_language", AsyncMock(return_value="en"))
        monkeypatch.setattr(group_invite_service, "get_email_service", lambda: AsyncMock(send=AsyncMock(side_effect=RuntimeError("smtp down"))))
        response = await group_invite_service.create_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN, email="ana@test.com")
        assert response.invite_url


class TestRevokeInvite:
    @pytest.mark.asyncio
    async def test_revoking_deletes_the_row_and_leaves_the_seat_in_place(self, monkeypatch):
        seat = _seat()
        deleted = AsyncMock()
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=seat))
        _patch_invite_repo(monkeypatch, delete_by_member=deleted)
        await group_invite_service.revoke_invite(AsyncMock(), _GROUP_ID, _MEMBER_ID, ADMIN)
        assert deleted.await_args.args[1] == _MEMBER_ID
        assert seat.is_active is True
        assert seat.user_id is None

    @pytest.mark.asyncio
    async def test_revoking_a_seat_from_another_group_is_not_found(self, monkeypatch):
        deleted = AsyncMock()
        _allow_admin(monkeypatch)
        _patch_group_repo(monkeypatch, get_member=AsyncMock(return_value=None))
        _patch_invite_repo(monkeypatch, delete_by_member=deleted)
        with pytest.raises(NotFoundError):
            await group_invite_service.revoke_invite(AsyncMock(), _GROUP_ID, 999, ADMIN)
        deleted.assert_not_awaited()


class TestTokenResolution:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "stored",
        [
            pytest.param(None, id="unknown"),
            pytest.param("consumed", id="already-claimed"),
            pytest.param("expired", id="past-its-window"),
        ],
    )
    async def test_every_unusable_token_gets_the_same_answer(self, monkeypatch, stored):
        # One error for all three on purpose: telling a holder which it was would let them probe
        # tokens, and the remedy ("ask for a new link") is identical.
        row = None if stored is None else _invite(consumed=stored == "consumed", expired=stored == "expired")
        _patch_group_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()))
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=row))
        with pytest.raises(InvalidTokenError):
            await group_invite_service.preview_invite(AsyncMock(), "some-token")

    @pytest.mark.asyncio
    async def test_the_lookup_is_by_hash_never_by_the_raw_token(self, monkeypatch):
        by_hash = AsyncMock(return_value=None)
        _patch_invite_repo(monkeypatch, get_by_hash=by_hash)
        with pytest.raises(InvalidTokenError):
            await group_invite_service.preview_invite(AsyncMock(), "raw-token-value")
        assert by_hash.await_args.args[1] == hashlib.sha256(b"raw-token-value").hexdigest()


class TestPreviewInvite:
    @pytest.mark.asyncio
    async def test_the_preview_names_the_group_the_seat_and_the_sender(self, monkeypatch):
        _patch_group_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite()))
        _patch_delivery(monkeypatch)
        preview = await group_invite_service.preview_invite(AsyncMock(), "token")
        assert (preview.group_name, preview.member_display_name, preview.invited_by_name) == ("Casa", "Ana", "Santi")

    @pytest.mark.asyncio
    async def test_the_preview_discloses_nothing_beyond_those_four_fields(self, monkeypatch):
        # An unauthenticated reader must not learn the roster, any member's identity, or any figure.
        _patch_group_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite()))
        _patch_delivery(monkeypatch)
        preview = await group_invite_service.preview_invite(AsyncMock(), "token")
        assert set(preview.model_dump()) == {"group_name", "group_kind", "member_display_name", "invited_by_name", "expires_at"}

    @pytest.mark.asyncio
    async def test_a_deleted_senders_name_is_simply_absent(self, monkeypatch):
        invite = _invite()
        invite.created_by = None
        _patch_group_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=invite))
        never_called = AsyncMock()
        monkeypatch.setattr(group_invite_service.user_repository, "get_by_id", never_called)
        preview = await group_invite_service.preview_invite(AsyncMock(), "token")
        assert preview.invited_by_name is None
        never_called.assert_not_awaited()


class TestAcceptInvite:
    @pytest.mark.asyncio
    async def test_accepting_links_the_seat_stamps_it_and_consumes_the_invite(self, monkeypatch):
        seat, invite = _seat(), _invite()
        saved_member, saved_invite = AsyncMock(), AsyncMock()
        _patch_group_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member=AsyncMock(return_value=seat),
            get_member_by_user=AsyncMock(return_value=None),
            save_member=saved_member,
        )
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=invite), save=saved_invite)
        session = AsyncMock()

        response = await group_invite_service.accept_invite(session, "token", JOINER)
        assert (response.group_id, response.member_id, response.group_name) == (_GROUP_ID, _MEMBER_ID, "Casa")
        assert seat.user_id == JOINER.id
        assert seat.joined_at is not None
        assert invite.consumed_at is not None
        # One transaction: the link and the consumption cannot land separately.
        session.commit.assert_awaited_once()
        saved_member.assert_awaited_once()
        saved_invite.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_the_same_link_cannot_be_used_twice(self, monkeypatch):
        _patch_group_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member=AsyncMock(return_value=_seat()))
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite(consumed=True)))
        with pytest.raises(InvalidTokenError):
            await group_invite_service.accept_invite(AsyncMock(), "token", JOINER)

    @pytest.mark.asyncio
    async def test_a_link_whose_seat_was_removed_cannot_be_claimed(self, monkeypatch):
        # remove_member deletes the pending invite, so this is defence in depth rather than the path.
        _patch_group_repo(monkeypatch, get_by_id=AsyncMock(return_value=_group()), get_member=AsyncMock(return_value=_seat(is_active=False)))
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite()))
        with pytest.raises(InvalidTokenError):
            await group_invite_service.accept_invite(AsyncMock(), "token", JOINER)

    @pytest.mark.asyncio
    async def test_a_seat_claimed_in_the_meantime_cannot_be_claimed_again(self, monkeypatch):
        _patch_group_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member=AsyncMock(return_value=_seat(user_id=99)),
        )
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite()))
        with pytest.raises(InvalidTokenError):
            await group_invite_service.accept_invite(AsyncMock(), "token", JOINER)

    @pytest.mark.asyncio
    async def test_an_existing_member_cannot_take_a_second_seat(self, monkeypatch):
        # One person is one member per group — two seats would split their history in half.
        held = GroupMember(id=7, group_id=_GROUP_ID, user_id=JOINER.id, display_name="Ana")
        seat = _seat()
        save_member = AsyncMock()
        _patch_group_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member=AsyncMock(return_value=seat),
            get_member_by_user=AsyncMock(return_value=held),
            save_member=save_member,
        )
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite()))
        with pytest.raises(GroupMembershipExistsError):
            await group_invite_service.accept_invite(AsyncMock(), "token", JOINER)
        # Refused before anything was written, so the invite stays usable by the right person.
        assert seat.user_id is None
        save_member.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_invited_address_does_not_have_to_match_the_accepters_account(self, monkeypatch):
        # The token IS the credential: an invite sent to one address is claimable by the account that
        # holds the link, whose Renly email is frequently a different one.
        seat = _seat()
        _patch_group_repo(
            monkeypatch,
            get_by_id=AsyncMock(return_value=_group()),
            get_member=AsyncMock(return_value=seat),
            get_member_by_user=AsyncMock(return_value=None),
        )
        _patch_invite_repo(monkeypatch, get_by_hash=AsyncMock(return_value=_invite(email="someone.else@test.com")))
        response = await group_invite_service.accept_invite(AsyncMock(), "token", JOINER)
        assert response.member_id == _MEMBER_ID
        assert seat.user_id == JOINER.id
