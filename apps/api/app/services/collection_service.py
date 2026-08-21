# Business logic for investment collections.

from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.investment_collection import InvestmentCollection
from app.models.user import User
from app.repositories import collection_repository, investment_repository


# Lists collections for the user with optional search and sorting. Returns each with its investment ids.
async def list_collections(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> list[tuple[InvestmentCollection, list[int]]]:
    collections = await collection_repository.list_by_user(session, user.id, search=search, sort_by=sort_by, sort_order=sort_order)
    # Batch-load membership for all collections in one query.
    collection_ids = [c.id for c in collections if c.id is not None]
    ids_by_collection = await collection_repository.get_investment_ids_by_collections(session, collection_ids)
    return [(c, ids_by_collection.get(c.id, [])) for c in collections]


# Fetches one collection by id. Raises NotFoundError if not found or not owned by user.
async def get_collection(
    session: AsyncSession,
    collection_id: int,
    user: User,
) -> tuple[InvestmentCollection, list[int]]:
    collection = await collection_repository.get_by_id(session, collection_id, user.id)
    if collection is None:
        raise NotFoundError("Collection not found")
    ids = await collection_repository.get_investment_ids_by_collection(session, collection.id)
    return (collection, ids)


# Creates a new collection for the user.
async def create_collection(
    session: AsyncSession,
    user: User,
    name: str,
    *,
    target_percentage: Decimal | None = None,
) -> InvestmentCollection:
    collection = InvestmentCollection(user_id=user.id, name=name, target_percentage=target_percentage)
    collection = await collection_repository.create(session, collection)
    await session.commit()
    return collection


# Updates an existing collection. Only provided fields are updated.
async def update_collection(
    session: AsyncSession,
    collection_id: int,
    user: User,
    *,
    name: str | None = None,
    target_percentage: Decimal | None = None,
) -> tuple[InvestmentCollection, list[int]]:
    collection = await collection_repository.get_by_id(session, collection_id, user.id)
    if collection is None:
        raise NotFoundError("Collection not found")
    if name is not None:
        collection.name = name
    collection.target_percentage = target_percentage
    await collection_repository.save(session, collection)
    await session.commit()
    await session.refresh(collection)
    ids = await collection_repository.get_investment_ids_by_collection(session, collection.id)
    return (collection, ids)


# Deletes a collection. Raises NotFoundError if not found or not owned.
async def delete_collection(
    session: AsyncSession,
    collection_id: int,
    user: User,
) -> None:
    collection = await collection_repository.get_by_id(session, collection_id, user.id)
    if collection is None:
        raise NotFoundError("Collection not found")
    await collection_repository.delete(session, collection)
    await session.commit()


# Replaces collection membership with the given investment ids. All investments must belong to the user.
async def set_collection_investments(
    session: AsyncSession,
    collection_id: int,
    user: User,
    investment_ids: list[int],
) -> None:
    collection = await collection_repository.get_by_id(session, collection_id, user.id)
    if collection is None:
        raise NotFoundError("Collection not found")
    # Batch validate all investment ids in one query.
    if investment_ids:
        found = await investment_repository.get_by_ids(session, investment_ids, user.id)
        if len(found) != len(investment_ids):
            missing = set(investment_ids) - {i.id for i in found}
            raise NotFoundError(f"Investments not found: {sorted(missing)}")
    await collection_repository.set_members(session, collection_id, investment_ids)
    await session.commit()
