from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.domain.list_scope import ListScope
from app.models.account import Account
from app.models.account_reconciliation import AccountReconciliation
from app.repositories.utils import apply_sort, scope_filter

_SORT_COLUMNS = {
    "name": Account.name,
    "type": Account.type,
    "currency": Account.currency,
    "opening_date": Account.opening_date,
}


# List accounts for a user with optional search, sorting, archive and scope filtering.
#
# The order is SCOPE-MAJOR (`pot_id` NULLS FIRST) with the caller's chosen sort applied within each
# scope, so the sections a grouped list draws stay contiguous — the same shape the investments list
# takes. No page tie-break is needed on top of it, unlike that list: this one is UNPAGINATED, so no row
# has to stay on a stable page.
#
# It no longer routes through apply_listing_filters, and that is the point: that helper hardcodes the
# owner match, which is exactly the predicate a dual-scope list has to replace. Its other four callers
# are entities with no `pot_id` column at all, so widening it would have offered them a scope argument
# describing a column they do not have.
#
# `private` is the default and every existing caller relies on it: seven other pages read this list as
# a PICKER of the caller's own accounts, and the group hub's own comment says so in as many words
# ("getAccounts is the caller's OWN accounts, and that is the whole point"). Grouped-by-default is a
# property of the LIST PAGE, which asks for it.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    pot_ids: list[int] | None = None,
    *,
    scope: ListScope = ListScope.private,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Account]:
    stmt = select(Account).where(scope_filter(Account, user_id, pot_ids or [], scope))
    if active_only:
        stmt = stmt.where(Account.is_active.is_(True))
    if search:
        stmt = stmt.where(Account.name.ilike(f"%{search}%"))
    stmt = apply_sort(
        stmt.order_by(Account.pot_id.nulls_first()),
        sort_by,
        sort_order,
        sort_columns=_SORT_COLUMNS,
        default_order=Account.name,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single account by id and user_id.
async def get_by_id(session: AsyncSession, account_id: int, user_id: int) -> Account | None:
    result = await session.execute(select(Account).where(Account.id == account_id, Account.user_id == user_id))
    return result.scalar_one_or_none()


# Get a single account by id WITHOUT pre-filtering by owner, for callers that must reach a co-owned
# account (whose user_id is NULL, so get_by_id can never match one). RLS still decides what is
# reachable at all; the caller decides which scope it needed and refuses the rest — which is the only
# safe split, because "is this the right account for this movement" is a question about the movement.
async def get_by_id_any_scope(session: AsyncSession, account_id: int) -> Account | None:
    result = await session.execute(select(Account).where(Account.id == account_id))
    return result.scalar_one_or_none()


# Get multiple accounts by id for a user (batch sibling of get_by_id).
async def get_by_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> list[Account]:
    if not account_ids:
        return []
    result = await session.execute(select(Account).where(Account.id.in_(account_ids), Account.user_id == user_id))
    return list(result.scalars().all())


# Get multiple accounts by id across ALL users. Deliberately unscoped, for the scheduler only: it
# resolves the default funding accounts of many users' plans in one query (the same shape as
# subscription_repository.list_active_due), and its caller re-checks each row's owner (SEC-4).
async def get_by_ids_across_users(session: AsyncSession, account_ids: list[int]) -> list[Account]:
    if not account_ids:
        return []
    result = await session.execute(select(Account).where(Account.id.in_(account_ids)))
    return list(result.scalars().all())


# Returns whether the user has any account (cheap existence check for the onboarding checklist;
# counts archived accounts too, so archiving a lone account doesn't un-complete the step).
async def exists_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Account.id).where(Account.user_id == user_id).limit(1))
    return result.first() is not None


# Insert a new account.
async def create(session: AsyncSession, account: Account) -> Account:
    session.add(account)
    await session.flush()
    return account


# Stage an account for update (caller commits).
async def save(session: AsyncSession, account: Account) -> None:
    session.add(account)


# Delete an account.
async def delete(session: AsyncSession, account: Account) -> None:
    await session.delete(account)


# Re-points everything the named pots hold to one user as private, returning how many moved. Called only
# from account deletion, when the leaving account holds the group's last active linked seat: at that
# moment nobody can ever see the pot again, so the honest outcome is that the holdings were always
# this user's. Runs BEFORE the account row goes — afterwards there is no user id left to assign.
async def reassign_pots_to_user(session: AsyncSession, pot_ids: list[int], user_id: int) -> int:
    if not pot_ids:
        return 0
    result = await session.execute(
        sa_update(Account).where(Account.pot_id.in_(pot_ids)).values(user_id=user_id, pot_id=None).execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


# Moves accounts between scopes, returning how many moved. `pot_id=None` moves them back to the
# caller as private, which is the only direction that needs a user id.
#
# The RLS-denormalized children are re-pointed in the SAME statement set, and that is not tidiness:
# account_reconciliations carry a copy of their parent's scope precisely so their policies do not
# have to join back to it, so a parent whose children still name the old scope is a row its own
# history has become invisible to. They are updated by PARENT id rather than by their own old scope,
# so a child that had somehow drifted is corrected rather than left behind.
async def move_to_scope(session: AsyncSession, ids: list[int], *, pot_id: int | None, user_id: int | None) -> int:
    if not ids:
        return 0
    values = {"pot_id": pot_id, "user_id": user_id}
    result = await session.execute(sa_update(Account).where(Account.id.in_(ids)).values(**values).execution_options(synchronize_session=False))
    await session.execute(
        sa_update(AccountReconciliation)
        .where(AccountReconciliation.account_id.in_(ids))
        .values(**values)
        .execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


# Batch sibling of get_by_ids that does NOT pre-filter by owner, for callers that must reach co-owned
# rows (whose user_id is NULL, so the owner-filtered version can never match one). RLS still decides
# what is reachable; the caller checks which scope it actually needed.
async def get_by_ids_any_scope(session: AsyncSession, ids: list[int]) -> list[Account]:
    if not ids:
        return []
    result = await session.execute(select(Account).where(Account.id.in_(ids)))
    return list(result.scalars().all())


# Namespace to call repository functions (e.g. account_repository.list_by_user).
class AccountRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    exists_by_user = staticmethod(exists_by_user)
    get_by_id = staticmethod(get_by_id)
    get_by_id_any_scope = staticmethod(get_by_id_any_scope)
    get_by_ids = staticmethod(get_by_ids)
    get_by_ids_across_users = staticmethod(get_by_ids_across_users)
    get_by_ids_any_scope = staticmethod(get_by_ids_any_scope)
    list_by_user = staticmethod(list_by_user)
    move_to_scope = staticmethod(move_to_scope)
    reassign_pots_to_user = staticmethod(reassign_pots_to_user)
    save = staticmethod(save)


# Singleton used by services to access account persistence.
account_repository = AccountRepository()
