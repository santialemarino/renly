# Data access for groups and their member seats.
#
# Unlike every other repository here, these queries are NOT filtered by user_id: a group's rows belong
# to the group, and the membership RLS policies (app_is_group_member) are what scope them to the
# requesting user. Two consequences worth keeping in mind while reading this file:
#   * a lookup that returns None may mean "does not exist" OR "not visible to you" — indistinguishable
#     by design, and the service maps both to NotFoundError so neither answer leaks the other;
#   * the two RLS-bootstrap use cases (creating a group, claiming a seat) run these functions on the
#     privileged session, because the membership row the policy reads does not exist yet.

from collections import defaultdict

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.models.group import Group, GroupMember, GroupMemberRole
from app.repositories.utils import chunked
from app.utils.pagination import apply_limit, capped


# Lists the groups visible to the session, newest first. RLS restricts this to the user's own groups.
async def list_visible(session: AsyncSession, *, limit: int | None = None) -> list[Group]:
    stmt = select(Group).order_by(Group.created_at.desc(), Group.id.desc())
    result = await session.execute(apply_limit(stmt, limit))
    return capped(list(result.scalars().all()), limit, "groups")


# Fetches a group by id. Returns None when it does not exist or is not visible to the session.
async def get_by_id(session: AsyncSession, group_id: int) -> Group | None:
    return await session.get(Group, group_id)


# Fetches several groups by id, for a caller naming them on a list it already has. The batch sibling of
# get_by_id, because the expenses list needs a name per shared row and a lookup per row is the N+1.
async def get_by_ids(session: AsyncSession, group_ids: list[int]) -> list[Group]:
    if not group_ids:
        return []
    groups: list[Group] = []
    for chunk in chunked(group_ids):
        result = await session.execute(select(Group).where(Group.id.in_(chunk)))
        groups.extend(result.scalars().all())
    return groups


# Persists a new group and flushes to get the id.
async def create(session: AsyncSession, group: Group) -> Group:
    session.add(group)
    await session.flush()
    return group


# Persists changes to an existing group.
async def save(session: AsyncSession, group: Group) -> None:
    session.add(group)


# Deletes a group. Members and invites go with it by FK CASCADE.
async def delete(session: AsyncSession, group: Group) -> None:
    await session.delete(group)


# --- The row-lock order, for the whole app ---
#
# Three row locks serialise the shared-money writes, and every path takes the ones it needs in ONE order,
# which is what keeps any two of them from waiting on each other:
#
#   1. the GROUP  (`lock` below)      — balances, settle-ups, the group's dollar rate, removing a member;
#   2. the POT    (pot_repository.lock) — every ledger write, a pot's dollar rate, editing a pot;
#   3. the SEAT   (`lock_members`)    — exclusive while a seat goes inactive or account-less, shared
#      while a ledger write hands that seat units.
#
# No path takes the group and a pot together, so 1 and 2 never meet; what makes the order hold is how
# the locks combine with the KEY SHARE locks Postgres takes implicitly, on the row a new row's foreign
# key points at. The group's lock is FOR NO KEY UPDATE, which those do NOT wait for, so a ledger write
# holding a pot and a seat can still insert its audit row naming the group while somebody holds the
# group. The seat's exclusive lock is FOR UPDATE, which they DO wait for, so a settlement or a shared
# expense naming a seat that is going waits for it to go — and then finds what it did. Removing a
# member takes the group THEN the seat. Account deletion takes EVERY active seat of the account (in the
# groups that outlive it and the ones that go with it) and only then the user row, which its delete
# locks and whose cascade writes those same seats; it takes no group lock, deciding nothing from a
# group's balances under one. Renaming the account into its seats takes the same two in the same order,
# the seats and then the user row (user_repository.lock), and no group lock either, because a seat's
# name decides nothing from a balance and moves no money.
#
# Takes a row lock on the group for the rest of the transaction, so two writers cannot derive the same
# balances and both act on them.
#
# The GROUP row rather than the rows the balance is summed from, because those span four tables and the
# rows a writer must not miss are the ones the other writer is about to INSERT — nothing can lock a row
# that does not exist yet. Every path that reads the balances to DECIDE something takes this first: a
# write-off capped at what is owed, an overpay waterfall allocating across buckets, and removing a
# member whose position must be zero. Recording an ordinary settlement does not, because it checks
# nothing against the balances — an overpayment is legal and simply flips the bucket.
#
# FOR NO KEY UPDATE (`key_share=True`) rather than FOR UPDATE: it excludes every other writer that
# takes it, and lets a row that merely REFERENCES the group (an audit entry a ledger write inserts) in
# without waiting — see the lock order above for why that is what keeps it deadlock-free.
#
# RLS applies, and it is `groups_member_isolation`'s USING that governs a locking read, so any active
# member may take it.
async def lock(session: AsyncSession, group_id: int) -> None:
    await session.execute(select(Group.id).where(Group.id == group_id).with_for_update(key_share=True))


# Locks seats, in id order so two callers locking overlapping sets cannot deadlock against each other,
# and re-reads them into whatever copies the session already holds.
#
# The SEAT is what a pot's ledger and a seat going inactive have in common, so it is what serialises
# them (third in the lock order above). A path that makes a seat inactive or account-less (removing a member, leaving, deleting the
# account) takes it EXCLUSIVELY before it counts the seat's units; a ledger write that hands a seat
# units takes it SHARED (`shared=True`) after its pot's lock and then checks the seat is still there.
# Whichever comes second waits for the first to commit and then sees what it did — so no write can hand
# units to a seat between the check that it owns none and the moment it goes. Shared, so ledger writes
# never wait on each other here; and nothing that holds a seat lock goes on to take a pot's, so the
# pot-then-seat order the ledger takes cannot meet its reverse.
#
# `populate_existing` because the caller may hold these seats already, loaded before the lock waited:
# the caller reads them again afterwards and must see what the lock waited for.
async def lock_members(session: AsyncSession, member_ids: list[int], *, shared: bool = False) -> None:
    if not member_ids:
        return
    await session.execute(
        select(GroupMember)
        .where(GroupMember.id.in_(sorted(set(member_ids))))
        .order_by(GroupMember.id)
        .with_for_update(read=shared)
        .execution_options(populate_existing=True)
    )


# Ids of the groups that become unreachable once this user's account is gone: groups they hold a seat
# in where no OTHER active, account-linked seat remains. Such a group can be read by nobody (the
# membership policy needs an active linked seat), administered by nobody, and re-entered by nobody, so
# nothing can ever remove it again — hence collecting the ids while the user still exists.
# `is_active` is part of the test on purpose: a former member who still has an account cannot see the
# group either, so leaving one behind would keep it just as unreachable.
async def list_orphaned_group_ids(session: AsyncSession, user_id: int) -> list[int]:
    others = (
        select(GroupMember.id)
        .where(
            GroupMember.group_id == Group.id,
            GroupMember.user_id.is_not(None),
            GroupMember.user_id != user_id,
            GroupMember.is_active,
        )
        .exists()
    )
    mine = select(GroupMember.id).where(GroupMember.group_id == Group.id, GroupMember.user_id == user_id).exists()
    result = await session.execute(select(Group.id).where(mine, ~others))
    return list(result.scalars().all())


# Deletes groups by id, with their seats and invites (FK CASCADE). Takes ids rather than rows because
# the account-deletion caller resolves them before the account goes and acts on them afterwards.
async def delete_by_ids(session: AsyncSession, group_ids: list[int]) -> None:
    if not group_ids:
        return
    await session.execute(sa_delete(Group).where(Group.id.in_(group_ids)))


# Lists every seat in a group — active and former, placeholders included — newest seat last.
async def list_members(session: AsyncSession, group_id: int) -> list[GroupMember]:
    result = await session.execute(select(GroupMember).where(GroupMember.group_id == group_id).order_by(GroupMember.id))
    return list(result.scalars().all())


# Returns {group_id: [member, ...]} for all given group ids in a single query (list-page fan-out).
async def list_members_by_groups(session: AsyncSession, group_ids: list[int]) -> dict[int, list[GroupMember]]:
    if not group_ids:
        return {}
    members_by_group: dict[int, list[GroupMember]] = defaultdict(list)
    for chunk in chunked(group_ids):
        result = await session.execute(select(GroupMember).where(GroupMember.group_id.in_(chunk)).order_by(GroupMember.id))
        for member in result.scalars().all():
            members_by_group[member.group_id].append(member)
    return dict(members_by_group)


# Fetches one seat by id, scoped to its group. Returns None when it does not exist or is not visible.
async def get_member(session: AsyncSession, group_id: int, member_id: int) -> GroupMember | None:
    result = await session.execute(select(GroupMember).where(GroupMember.id == member_id, GroupMember.group_id == group_id))
    return result.scalar_one_or_none()


# Every ACTIVE seat this user holds, as rows. Used by the guards that run before a seat or an account
# goes away and need the group each seat belongs to, not only its id.
# Deliberately a second query rather than the source of list_active_member_ids below: that one runs on
# the expenses list for every request and wants the narrowest projection there is.
async def list_active_members(session: AsyncSession, user_id: int) -> list[GroupMember]:
    result = await session.execute(select(GroupMember).where(GroupMember.user_id == user_id, GroupMember.is_active))
    return list(result.scalars().all())


# Every ACTIVE seat this user holds, across every group. The /expenses union needs the ids to find the
# caller's own shares, and resolving them here rather than joining group_members inside that union is
# what lets the splits' member index do the work — measured at roughly half the time on a 55,000-row
# list, because the join makes Postgres scan every split in the database instead.
async def list_active_member_ids(session: AsyncSession, user_id: int) -> list[int]:
    result = await session.execute(select(GroupMember.id).where(GroupMember.user_id == user_id, GroupMember.is_active))
    return [row[0] for row in result.all()]


# Returns whether the user holds an ACTIVE seat in any group (cheap existence check for the onboarding
# checklist's optional sharing step). The same predicate as list_active_member_ids narrowed to a LIMIT 1,
# and active for the same reason the scope controls test it: a former member belongs to no group, so
# leaving one un-completes the step rather than leaving it ticked on a group they can no longer see.
async def exists_active_member_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(GroupMember.id).where(GroupMember.user_id == user_id, GroupMember.is_active).limit(1))
    return result.first() is not None


# Fetches the seat a user holds in a group, active or not. Returns None when they hold none.
async def get_member_by_user(session: AsyncSession, group_id: int, user_id: int) -> GroupMember | None:
    result = await session.execute(select(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == user_id))
    return result.scalar_one_or_none()


# Counts the group's ACTIVE admin seats. The service uses this to refuse the change that would leave a
# group with none — deleting, deactivating or demoting its last one.
async def count_active_admins(session: AsyncSession, group_id: int) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(GroupMember)
        .where(
            GroupMember.group_id == group_id,
            GroupMember.role == GroupMemberRole.admin,
            GroupMember.is_active,
        )
    )
    return result.scalar_one()


# Persists a new seat and flushes to get the id.
async def create_member(session: AsyncSession, member: GroupMember) -> GroupMember:
    session.add(member)
    await session.flush()
    return member


# Persists changes to an existing seat.
async def save_member(session: AsyncSession, member: GroupMember) -> None:
    session.add(member)


# Namespace to call repository functions (e.g. group_repository.list_visible).
class GroupRepository:
    count_active_admins = staticmethod(count_active_admins)
    create = staticmethod(create)
    create_member = staticmethod(create_member)
    delete = staticmethod(delete)
    delete_by_ids = staticmethod(delete_by_ids)
    exists_active_member_by_user = staticmethod(exists_active_member_by_user)
    get_by_id = staticmethod(get_by_id)
    get_by_ids = staticmethod(get_by_ids)
    get_member = staticmethod(get_member)
    get_member_by_user = staticmethod(get_member_by_user)
    list_active_member_ids = staticmethod(list_active_member_ids)
    list_active_members = staticmethod(list_active_members)
    list_members = staticmethod(list_members)
    list_members_by_groups = staticmethod(list_members_by_groups)
    list_orphaned_group_ids = staticmethod(list_orphaned_group_ids)
    list_visible = staticmethod(list_visible)
    lock = staticmethod(lock)
    lock_members = staticmethod(lock_members)
    save = staticmethod(save)
    save_member = staticmethod(save_member)


# Singleton used by services to access group persistence.
group_repository = GroupRepository()
