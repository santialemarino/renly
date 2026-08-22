# Data access for group-seat invites.
#
# Like group_repository, these queries carry no user_id filter — the membership RLS policy scopes them.
# get_by_hash is the exception that must run on the privileged session: the person redeeming a token is
# not a member yet, so the policy hides the row from them until the seat is claimed.

from collections import defaultdict

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.group_invite import GroupInvite


# Lists the invites outstanding in a group, newest first.
async def list_by_group(session: AsyncSession, group_id: int) -> list[GroupInvite]:
    result = await session.execute(
        select(GroupInvite).where(GroupInvite.group_id == group_id).order_by(GroupInvite.created_at.desc(), GroupInvite.id.desc())
    )
    return list(result.scalars().all())


# Returns {group_id: [invite, ...]} for all given group ids in a single query (list-page fan-out).
async def list_by_groups(session: AsyncSession, group_ids: list[int]) -> dict[int, list[GroupInvite]]:
    if not group_ids:
        return {}
    result = await session.execute(select(GroupInvite).where(GroupInvite.group_id.in_(group_ids)))
    invites_by_group: dict[int, list[GroupInvite]] = defaultdict(list)
    for invite in result.scalars().all():
        invites_by_group[invite.group_id].append(invite)
    return dict(invites_by_group)


# Fetches the invite held by one seat, if any. UNIQUE (member_id) makes this at most one row.
async def get_by_member(session: AsyncSession, member_id: int) -> GroupInvite | None:
    result = await session.execute(select(GroupInvite).where(GroupInvite.member_id == member_id))
    return result.scalar_one_or_none()


# Fetches an invite by its SHA-256 token hash. Returns None when no invite matches. Runs on the
# privileged session: the redeemer is not a member yet, so RLS would hide the row from them.
async def get_by_hash(session: AsyncSession, token_hash: str) -> GroupInvite | None:
    result = await session.execute(select(GroupInvite).where(GroupInvite.token_hash == token_hash))
    return result.scalar_one_or_none()


# Persists a new invite and flushes to get the id.
async def create(session: AsyncSession, invite: GroupInvite) -> GroupInvite:
    session.add(invite)
    await session.flush()
    return invite


# Persists changes to an existing invite (rotating its token, or marking it consumed).
async def save(session: AsyncSession, invite: GroupInvite) -> None:
    session.add(invite)


# Deletes a seat's invite, if any. Revoking removes the row rather than flagging it: the seat stays as
# the name-only member it already was, and there is no revoked state anything reads.
async def delete_by_member(session: AsyncSession, member_id: int) -> None:
    await session.execute(sa_delete(GroupInvite).where(GroupInvite.member_id == member_id))


# Namespace to call repository functions (e.g. group_invite_repository.get_by_hash).
class GroupInviteRepository:
    create = staticmethod(create)
    delete_by_member = staticmethod(delete_by_member)
    get_by_hash = staticmethod(get_by_hash)
    get_by_member = staticmethod(get_by_member)
    list_by_group = staticmethod(list_by_group)
    list_by_groups = staticmethod(list_by_groups)
    save = staticmethod(save)


# Singleton used by services to access group-invite persistence.
group_invite_repository = GroupInviteRepository()
