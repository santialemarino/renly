# Data access for pots and their per-member permissions.
#
# Like group_repository and unlike every other repository here, these queries are NOT filtered by
# user_id: a pot's rows belong to the pot, and the dual-scope RLS policies (app_can_view_pot /
# app_can_write_pot) are what scope them to the requesting user. So a lookup returning None may mean
# "does not exist" OR "not visible to you", indistinguishable by design, and the service maps both to
# NotFoundError so neither answer leaks the other.
#
# Creating a pot runs on the privileged session: its first permission row is exactly what the policy
# reads, so the insert cannot satisfy its own predicate — the same bootstrap group creation has.

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from app.models.account import Account
from app.models.investment import Investment
from app.models.pot import Pot, PotMemberPermission


# Lists the pots visible to the session, newest first. RLS restricts this to pots the user may see.
async def list_visible(session: AsyncSession) -> list[Pot]:
    result = await session.execute(select(Pot).order_by(Pot.created_at.desc(), Pot.id.desc()))
    return list(result.scalars().all())


# Every pot in the database, for the privileged scheduler (the overdue-valuation reminder has to
# consider all of them). Deliberately its own function rather than calling list_visible on the
# privileged session: that name promises scoping, and a name promising scoping used where nothing
# scopes it is how a future change to the scoping silently stops applying to a background job.
async def list_all(session: AsyncSession) -> list[Pot]:
    result = await session.execute(select(Pot).order_by(Pot.id))
    return list(result.scalars().all())


# Lists the visible pots belonging to one group.
async def list_by_group(session: AsyncSession, group_id: int) -> list[Pot]:
    result = await session.execute(select(Pot).where(Pot.group_id == group_id).order_by(Pot.created_at.desc(), Pot.id.desc()))
    return list(result.scalars().all())


# Fetches a pot by id. Returns None when it does not exist or is not visible to the session.
async def get_by_id(session: AsyncSession, pot_id: int) -> Pot | None:
    return await session.get(Pot, pot_id)


# Persists a new pot and flushes to get the id.
async def create(session: AsyncSession, pot: Pot) -> Pot:
    session.add(pot)
    await session.flush()
    return pot


# Persists changes to an existing pot.
async def save(session: AsyncSession, pot: Pot) -> None:
    session.add(pot)


# Deletes a pot. Refused by the database while any holding still points at it (every pot_id foreign
# key is ON DELETE RESTRICT), which is why the service counts holdings first and raises a real error.
async def delete(session: AsyncSession, pot: Pot) -> None:
    await session.delete(pot)


# How many investments and accounts a pot holds. One query per table rather than a union: the two are
# counted separately nowhere else, and a union of two different models buys nothing here.
async def count_holdings(session: AsyncSession, pot_id: int) -> int:
    investments = await session.execute(select(func.count()).select_from(Investment).where(Investment.pot_id == pot_id))
    accounts = await session.execute(select(func.count()).select_from(Account).where(Account.pot_id == pot_id))
    return int(investments.scalar_one()) + int(accounts.scalar_one())


# Everything a pot holds, investments and accounts, ARCHIVED ONES INCLUDED — the read behind the pot
# page's holdings list and the move-out picker.
#
# Deliberately unfiltered where the two NAV queries below filter on is_active. An archived holding
# still points at the pot, so it still blocks deleting the pot (count_holdings counts it) and it still
# has to be movable back out; a read that hid it would show an empty pot that refuses to be deleted,
# with nothing on screen explaining why. It contributes nothing to the NAV either way, which is the
# NAV queries' concern and not this one's.
async def list_holdings(session: AsyncSession, pot_id: int) -> tuple[list[Investment], list[Account]]:
    investments = await session.execute(select(Investment).where(Investment.pot_id == pot_id).order_by(Investment.name, Investment.id))
    accounts = await session.execute(select(Account).where(Account.pot_id == pot_id).order_by(Account.name, Account.id))
    return (list(investments.scalars().all()), list(accounts.scalars().all()))


# The ACTIVE investments a pot holds, for the NAV query. Returns whole rows rather than ids because a
# valuation now also has to say which composition bucket each holding contributes to, and `category`
# comes free in the same query — a second read to fetch it would be a second answer to "what does this
# pot hold".
async def list_active_investments(session: AsyncSession, pot_id: int) -> list[Investment]:
    result = await session.execute(select(Investment).where(Investment.pot_id == pot_id, Investment.is_active.is_(True)).order_by(Investment.id))
    return list(result.scalars().all())


# The accounts a pot holds, for the NAV query. Returns whole rows because a balance needs each
# account's currency and opening date, not just its id.
async def list_accounts(session: AsyncSession, pot_id: int) -> list[Account]:
    result = await session.execute(select(Account).where(Account.pot_id == pot_id, Account.is_active.is_(True)))
    return list(result.scalars().all())


# Every permission row for one pot.
async def list_permissions(session: AsyncSession, pot_id: int) -> list[PotMemberPermission]:
    result = await session.execute(select(PotMemberPermission).where(PotMemberPermission.pot_id == pot_id))
    return list(result.scalars().all())


# Permission rows for several pots at once, keyed by pot id, so a list page costs one query rather
# than one per pot.
async def list_permissions_by_pots(session: AsyncSession, pot_ids: list[int]) -> dict[int, list[PotMemberPermission]]:
    if not pot_ids:
        return {}
    result = await session.execute(select(PotMemberPermission).where(PotMemberPermission.pot_id.in_(pot_ids)))
    grouped: dict[int, list[PotMemberPermission]] = defaultdict(list)
    for permission in result.scalars().all():
        grouped[permission.pot_id].append(permission)
    return dict(grouped)


# One member's permission row for one pot, or None when they have none and the pot's visibility
# default applies instead.
async def get_permission(session: AsyncSession, pot_id: int, member_id: int) -> PotMemberPermission | None:
    result = await session.execute(
        select(PotMemberPermission).where(PotMemberPermission.pot_id == pot_id, PotMemberPermission.member_id == member_id)
    )
    return result.scalars().first()


# Persists a permission row, new or existing. session.merge rather than add, because the composite
# primary key means the caller may legitimately hand back a row it just read or one it built fresh.
async def save_permission(session: AsyncSession, permission: PotMemberPermission) -> PotMemberPermission:
    merged = await session.merge(permission)
    await session.flush()
    return merged


# Removes a member's explicit permission row, dropping them back to the pot's visibility default.
async def delete_permission(session: AsyncSession, permission: PotMemberPermission) -> None:
    await session.delete(permission)


# Namespace to call repository functions (e.g. pot_repository.list_visible).
class PotRepository:
    count_holdings = staticmethod(count_holdings)
    create = staticmethod(create)
    delete = staticmethod(delete)
    delete_permission = staticmethod(delete_permission)
    get_by_id = staticmethod(get_by_id)
    get_permission = staticmethod(get_permission)
    list_accounts = staticmethod(list_accounts)
    list_active_investments = staticmethod(list_active_investments)
    list_all = staticmethod(list_all)
    list_by_group = staticmethod(list_by_group)
    list_holdings = staticmethod(list_holdings)
    list_permissions = staticmethod(list_permissions)
    list_permissions_by_pots = staticmethod(list_permissions_by_pots)
    list_visible = staticmethod(list_visible)
    save = staticmethod(save)
    save_permission = staticmethod(save_permission)


# Singleton used by services to access pot persistence.
pot_repository = PotRepository()
