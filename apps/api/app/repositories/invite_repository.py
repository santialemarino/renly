# Data access for admin invites (invite-only access gate).

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.invite import Invite


# Lists every invite, newest first (admin invite management view).
async def list_all(session: AsyncSession) -> list[Invite]:
    result = await session.execute(select(Invite).order_by(Invite.created_at.desc()))
    return list(result.scalars().all())


# Fetches an invite by id. Returns None when no invite matches.
async def get_by_id(session: AsyncSession, invite_id: int) -> Invite | None:
    return await session.get(Invite, invite_id)


# Fetches an invite by email. Lowercases the input so lookups are case-insensitive.
async def get_by_email(session: AsyncSession, email: str) -> Invite | None:
    result = await session.execute(select(Invite).where(Invite.email == email.lower()))
    return result.scalar_one_or_none()


# Fetches an invite by its SHA-256 token hash. Returns None when no invite matches.
async def get_by_hash(session: AsyncSession, token_hash: str) -> Invite | None:
    result = await session.execute(select(Invite).where(Invite.token_hash == token_hash))
    return result.scalar_one_or_none()


# Persists a new invite and flushes to get the id.
async def create(session: AsyncSession, invite: Invite) -> Invite:
    session.add(invite)
    await session.flush()
    return invite


# Persists changes to an existing invite (e.g. rotating the token, marking it consumed or revoked).
async def save(session: AsyncSession, invite: Invite) -> None:
    session.add(invite)


# Namespace to call repository functions (e.g. invite_repository.get_by_hash).
class InviteRepository:
    create = staticmethod(create)
    get_by_email = staticmethod(get_by_email)
    get_by_hash = staticmethod(get_by_hash)
    get_by_id = staticmethod(get_by_id)
    list_all = staticmethod(list_all)
    save = staticmethod(save)


# Singleton used by services to access invite persistence.
invite_repository = InviteRepository()
