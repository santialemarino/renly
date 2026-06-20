# Authenticated account self-service (AUTH-8 / AUTH-6): change password, change email, export data,
# and delete the account. Each sensitive action re-verifies the current password.

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import InvalidCredentialsError, PasswordBreachedError
from app.models.user import User
from app.models.utils import utcnow
from app.repositories import export_repository, user_repository
from app.services import auth_service


# Changes the password after re-verifying the current one (AUTH-8). Rejects breached passwords
# (AUTH-3) and bumps session_epoch so every other existing session is logged out.
async def change_password(session: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if not auth_service.verify_password(current_password, user.password_hash):
        raise InvalidCredentialsError()
    if await auth_service.is_password_breached(new_password):
        raise PasswordBreachedError()
    user.password_hash = auth_service.hash_password(new_password)
    user.session_epoch += 1
    await user_repository.save(session, user)
    await session.commit()


# Starts an email change after re-verifying the current password (AUTH-8); the address only switches
# once the new one is confirmed via the emailed link. Runs the change request on the privileged
# session so the target-address availability check can see every account (bypasses RLS).
async def change_email(session: AsyncSession, user: User, current_password: str, new_email: str) -> None:
    if not auth_service.verify_password(current_password, user.password_hash):
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
# (AUTH-6). FK ON DELETE CASCADE removes every owned row.
async def delete_account(session: AsyncSession, user: User, password: str, confirmation: str) -> None:
    if not auth_service.verify_password(password, user.password_hash):
        raise InvalidCredentialsError()
    if confirmation.strip().lower() != user.email.lower():
        raise InvalidCredentialsError("Confirmation does not match your email.")
    await user_repository.delete(session, user)
    await session.commit()
