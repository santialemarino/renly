# Data access for investment collections and membership.

from collections import defaultdict

from sqlalchemy import delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.investment_collection import InvestmentCollection, InvestmentCollectionMember
from app.repositories.utils import apply_sort

_SORT_COLUMNS = {
    "name": InvestmentCollection.name,
}


# Lists collections for a user with optional search and sorting.
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> list[InvestmentCollection]:
    stmt = select(InvestmentCollection).where(InvestmentCollection.user_id == user_id)
    if search:
        stmt = stmt.where(InvestmentCollection.name.ilike(f"%{search}%"))
    stmt = apply_sort(stmt, sort_by, sort_order, sort_columns=_SORT_COLUMNS, default_order=InvestmentCollection.id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Fetches a single collection by id and user_id. Returns None if not found or not owned.
async def get_by_id(
    session: AsyncSession,
    collection_id: int,
    user_id: int,
) -> InvestmentCollection | None:
    result = await session.execute(
        select(InvestmentCollection).where(
            InvestmentCollection.id == collection_id,
            InvestmentCollection.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


# Returns investment ids that belong to the collection.
async def get_investment_ids_by_collection(session: AsyncSession, collection_id: int) -> list[int]:
    stmt = select(InvestmentCollectionMember.investment_id).where(InvestmentCollectionMember.collection_id == collection_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Returns {collection_id: [investment_id, ...]} for all given collection IDs in a single query.
async def get_investment_ids_by_collections(session: AsyncSession, collection_ids: list[int]) -> dict[int, list[int]]:
    if not collection_ids:
        return {}
    result = await session.execute(
        select(InvestmentCollectionMember.collection_id, InvestmentCollectionMember.investment_id).where(
            InvestmentCollectionMember.collection_id.in_(collection_ids)
        )
    )
    ids_by_collection: dict[int, list[int]] = defaultdict(list)
    for row in result.all():
        ids_by_collection[row.collection_id].append(row.investment_id)
    return dict(ids_by_collection)


# Persists a new collection and flushes to get the id.
async def create(session: AsyncSession, collection: InvestmentCollection) -> InvestmentCollection:
    session.add(collection)
    await session.flush()
    return collection


# Persists changes to an existing collection.
async def save(session: AsyncSession, collection: InvestmentCollection) -> None:
    session.add(collection)


# Deletes a collection. Members are removed by FK CASCADE.
async def delete(session: AsyncSession, collection: InvestmentCollection) -> None:
    await session.delete(collection)


# Replaces membership: delete all for collection, then add (collection_id, inv_id) for each id.
async def set_members(
    session: AsyncSession,
    collection_id: int,
    investment_ids: list[int],
) -> None:
    await session.execute(sa_delete(InvestmentCollectionMember).where(InvestmentCollectionMember.collection_id == collection_id))
    for inv_id in investment_ids:
        session.add(InvestmentCollectionMember(collection_id=collection_id, investment_id=inv_id))


# Replaces collection membership for an investment: removes all existing, adds new collection_ids.
async def set_collections_for_investment(
    session: AsyncSession,
    investment_id: int,
    collection_ids: list[int],
) -> None:
    await session.execute(sa_delete(InvestmentCollectionMember).where(InvestmentCollectionMember.investment_id == investment_id))
    for collection_id in collection_ids:
        session.add(InvestmentCollectionMember(investment_id=investment_id, collection_id=collection_id))


# Namespace to call repository functions (e.g. collection_repository.list_by_user).
class CollectionRepository:
    create = staticmethod(create)
    delete = staticmethod(delete)
    get_by_id = staticmethod(get_by_id)
    get_investment_ids_by_collection = staticmethod(get_investment_ids_by_collection)
    get_investment_ids_by_collections = staticmethod(get_investment_ids_by_collections)
    list_by_user = staticmethod(list_by_user)
    save = staticmethod(save)
    set_collections_for_investment = staticmethod(set_collections_for_investment)
    set_members = staticmethod(set_members)


# Singleton used by services to access collection persistence.
collection_repository = CollectionRepository()
