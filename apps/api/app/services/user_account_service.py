# Authenticated account self-service (AUTH-8 / AUTH-6): change password, change email, export data,
# and delete the account. Each sensitive action re-verifies the current password.

import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import InvalidCredentialsError, PasswordBreachedError
from app.models.group import Group, GroupMember
from app.models.shared_audit import AuditAction, AuditEntityType
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import export_repository, group_repository, invite_repository, user_repository
from app.services import auth_service, group_money_service, group_settlement_service, pot_service, shared_audit_service

logger = logging.getLogger(__name__)


# Changes the password after re-verifying the current one (AUTH-8). Rejects breached passwords
# (AUTH-3) and bumps session_epoch so every other existing session is logged out.
async def change_password(session: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if not await auth_service.verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError()
    if await auth_service.is_password_breached(new_password):
        raise PasswordBreachedError()
    user.password_hash = await auth_service.hash_password(new_password)
    user.session_epoch += 1
    await user_repository.save(session, user)
    await session.commit()


# Whether a seat still carries the account's name: the same text after the trimming every name gets on
# the way in (RequestBase strips both), compared exactly.
#   * Case-sensitive, because a seat reading "SANTI" beside an account called "Santi" was most likely
#     spelled that way on purpose, by the user or by whoever named the seat.
#   * Not Unicode-normalised, matching how both names are stored: neither is NFC-folded nor stripped of
#     invisible characters anywhere. The seat this looks for started as a copy of the account name
#     (creating a group seats its creator under it), so it is equal already; a lookalike in another
#     normal form, or with a zero-width character in it, was typed separately and is left alone.
def _carries_account_name(seat: GroupMember, account_name: str) -> bool:
    return seat.display_name.strip() == account_name.strip()


# The groups where the user's seat still carries their account name — what renaming the account with
# `rename_group_seats` would rename. Active seats only: a former member's seat is in a group they can no
# longer see, and its name is the group's record of them. Read on the request session, where the
# membership policy already limits the rows to groups the user is in. Sorted by group name.
async def list_groups_using_account_name(session: AsyncSession, user: User) -> list[Group]:
    seats = [seat for seat in await group_repository.list_active_members(session, user.id) if _carries_account_name(seat, user.name)]
    groups = await group_repository.get_by_ids(session, [seat.group_id for seat in seats])
    return sorted(groups, key=lambda group: (group.name.casefold(), group.id))


# Renames the user, and with `rename_group_seats` also every seat of theirs that still carries the OLD
# name, in one transaction. Returns the user and how many seats were renamed.
#
# The account name is read live wherever it shows (the account page, group invites, the export), so
# nothing else follows it. A seat's display name is the group's own, which is why following it is
# opt-in, and limited to the seats nobody renamed: a nickname, a name an admin chose, or a placeholder
# name the seat had before the account claimed it all stay. Past notifications keep the name they were
# sent with.
#
# The seats are locked before anything is decided (group_repository, "The row-lock order": the seats,
# then the user row). Both locks re-read their rows, so the match is made against what is committed
# now rather than what the request loaded:
#   * an admin renaming one of these seats at the same moment either commits first — the seat no longer
#     matches and keeps the admin's name — or waits for this rename and then applies theirs on top;
#   * two renames of the same account serialise, and the second matches against the name the first
#     left, so the seats never stop agreeing with the account they followed.
# Nothing can collide: a seat's name is not unique in its group (an admin can already give two members
# the same one) and shares the account name's 255-character limit, so every seat that matches is renamed.
# The flag is ignored when the name does not change. Any failure rolls back everything, the account
# name included: the request either did what the user asked or nothing.
#
# Each renamed seat leaves an entry in its group's activity feed, as an admin's rename does; nobody is
# notified.
async def update_profile(session: AsyncSession, user: User, name: str, *, rename_group_seats: bool = False) -> tuple[User, int]:
    renamed: list[GroupMember] = []
    if rename_group_seats:
        seats = await group_repository.list_active_members(session, user.id)
        await group_repository.lock_members(session, [seat.id for seat in seats])
        await user_repository.lock(session, user.id)
        if name != user.name:
            # `is_active` is read again here, after the lock, on purpose: a removal or a leave that
            # committed while this waited has deactivated the seat, and the membership policy now hides it
            # from this session's UPDATE, which would fail on a row that silently matched nothing. The
            # list above was read before the wait, so it cannot have known.
            renamed = [seat for seat in seats if seat.is_active and _carries_account_name(seat, user.name)]
    for seat in renamed:
        # The entry names both names: the feed reads its actor from the live roster, which by then says
        # the new one, so the old one would otherwise be lost from the sentence.
        previous = seat.display_name
        seat.display_name = name
        await group_repository.save_member(session, seat)
        await shared_audit_service.record(
            session,
            group_id=seat.group_id,
            actor=user,
            entity_type=AuditEntityType.group_member,
            action=AuditAction.updated,
            entity_id=seat.id,
            payload={"member": name, "from": previous, "variant": "account_name"},
        )
    user.name = name
    await user_repository.save(session, user)
    await session.commit()
    await session.refresh(user)
    return user, len(renamed)


# Starts an email change after re-verifying the current password (AUTH-8); the address only switches
# once the new one is confirmed via the emailed link. Runs the change request on the privileged
# session so the target-address availability check can see every account (bypasses RLS).
async def change_email(session: AsyncSession, user: User, current_password: str, new_email: str) -> None:
    if not await auth_service.verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError()
    await auth_service.request_email_change(session, user, new_email)


# Builds the user's full data export as a JSON-serializable dict (AUTH-6). Excludes secrets: the
# user's password hash and the api-key hashes/prefixes never leave the system.
async def export_user_data(session: AsyncSession, user: User) -> dict[str, Any]:
    raw = await export_repository.dump_user_data(session, user.id)
    api_keys = [
        {
            "id": key.id,
            "name": key.name,
            "created_at": key.created_at,
            "last_used_at": key.last_used_at,
            "is_active": key.is_active,
        }
        for key in raw.pop("api_keys", [])
    ]
    return {
        "exported_at": utcnow(),
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "plan": user.plan,
            "email_verified_at": user.email_verified_at,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        },
        "api_keys": api_keys,
        **raw,
    }


# Permanently deletes the account after re-verifying the password and a typed email confirmation
# (AUTH-6). FK ON DELETE CASCADE removes every owned row. Two things survive the cascade on purpose and
# are handled here: the invite that created this account (so deletion leaves no orphaned "accepted"
# invite), and shared groups — `group_members.user_id` is ON DELETE SET NULL because a group belongs to
# its members rather than to whoever created it, so a group the deleted account SHARED with someone
# else must outlive them, reverting their seat to a name-only placeholder. Both live on the privileged
# session: the invite is FK'd to the inviting admin, and a group is reachable only through membership.
async def delete_account(session: AsyncSession, admin_session: AsyncSession, user: User, password: str, confirmation: str) -> None:
    if not await auth_service.verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if confirmation.strip().lower() != user.email.lower():
        raise InvalidCredentialsError("Confirmation does not match your email.")
    email = user.email
    # Every ACTIVE seat the account holds is locked first, on the account's OWN session, and held until
    # its deletion commits below — in the groups that survive it AND in the ones that go with it. The
    # deletion's cascade (`user_id` SET NULL) writes every one of those seats, so each must be held
    # before the user row is touched: a rename of this account takes the same seats first and the user
    # row after (update_profile), and a deletion holding only some of them met it the other way round —
    # the rename holding a seat in a dying group, waiting on a surviving one, while the cascade waited on
    # the dying one. Taken in id order, as every seat lock is (group_repository, "The row-lock order").
    # It also stops every ledger write that hands a seat units (they take that seat's lock after their
    # pot's, group_repository.lock_members) between the checks below and the moment the seats lose their
    # account; one that waited then finds them gone. The seats only, no group lock.
    # Read on the privileged session because everything else in this flow is; the account still exists,
    # so the request session would see the same rows.
    active_seats = await group_repository.list_active_members(admin_session, user.id)
    await group_repository.lock_members(session, [seat.id for seat in active_seats])
    # Resolved BEFORE the account goes: once the user row is deleted their seats read user_id NULL, and
    # "was this the group's only account-holder" stops being answerable.
    orphan_group_ids = await group_repository.list_orphaned_group_ids(admin_session, user.id)
    # Everything those groups' pots hold is re-pointed to this user as PRIVATE, before anything is
    # deleted — parents and their scope-denormalized children together, so no row is left naming a pot
    # its parent has left. Three reasons it has to happen here and in this order:
    #   * every pot_id foreign key is ON DELETE RESTRICT, so deleting an orphaned group that still
    #     owns holdings would simply fail — and CASCADE would have been far worse, destroying real
    #     money records to satisfy a cleanup;
    #   * once the user row is gone there is no id left to assign the holdings to;
    #   * when the last account-linked seat leaves, the remaining seats are placeholders with no way
    #     to ever see the money again, so the honest reading is that it was always this user's — and
    #     it then goes with the rest of their data on the cascade below.
    await pot_service.absorb_group_pots(admin_session, orphan_group_ids, user.id)
    # D24's balance check, on the groups that SURVIVE this deletion. An orphaned group is excluded on
    # purpose: nobody is left to be owed anything in it, and its money has just been absorbed above.
    # A surviving group is the case that matters — deleting the account would revert the seat to a
    # name-only placeholder while the person on the other side still holds a real claim against it, and
    # no settlement could ever clear it. Settle or write it off first.
    surviving_seats = [seat for seat in active_seats if seat.group_id not in set(orphan_group_ids)]
    await group_settlement_service.ensure_no_outstanding_balance(admin_session, surviving_seats)
    # And no pot share left behind in a surviving group. Deleting the account turns the seat into a
    # name-only placeholder, which no change of split or of a pot's dollar rate waits for — so the other
    # owners could reshape a pot that is still partly this person's, and nobody could ever buy the share
    # out on their behalf. Settle it first, with a buy-out or a take-out. (An orphaned group's pots were
    # absorbed above, so they are not asked about.)
    await pot_service.ensure_no_units(admin_session, surviving_seats, for_account=True)
    await admin_session.commit()
    # Clear the invite first, on its own (privileged) transaction. The deletes span two connections so
    # they can't be atomic; ordering invite-first makes the only partial-failure state benign — an
    # invite with no account self-heals on re-invite, whereas deleting the user first and then failing
    # the invite delete would leave exactly the orphan this guards against.
    await invite_repository.delete_by_email(admin_session, email)
    await admin_session.commit()
    await user_repository.delete(session, user)
    await session.commit()
    # Each surviving group's pending change of dollar rate stops waiting for the seat that just lost its
    # account, and applies if it was the last one it waited for. After the delete, because only then does
    # the seat read as account-less; with no actor, because the account is gone. A failure here must not
    # fail a deletion that has already happened: the proposal stays pending, and any member still waited
    # on can apply it by agreeing (the backstop in agree_dollar_rate).
    for group_id in sorted({seat.group_id for seat in surviving_seats}):
        try:
            applied = await group_money_service.settle_dollar_rate_proposal(admin_session, group_id, None)
            await admin_session.commit()
            if applied is not None:
                await group_money_service.announce_dollar_rate_applied(applied)
        except Exception:
            logger.exception("Settling the dollar-rate proposal of group %s after an account deletion failed.", group_id)
            await admin_session.rollback()
    # The orphaned groups go LAST, for the same fail-benign reason inverted: dropping them before the
    # account and then failing the account delete would destroy a live user's groups, whereas failing
    # here leaves unreachable rows — which is precisely the state that existed before this cleanup.
    # Both partial failures are benign only because the absorption above moved every child with its
    # parent: a failure after its commit leaves a live user holding private accounts and investments
    # whose whole history is private too, and pots nothing names any more, so the groups can still be
    # deleted later.
    await group_repository.delete_by_ids(admin_session, orphan_group_ids)
    await admin_session.commit()
