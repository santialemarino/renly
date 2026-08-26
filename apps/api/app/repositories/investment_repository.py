# Data access for investments.

from sqlalchemy import String, cast, func
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.investment import Investment, InvestmentCategory
from app.models.investment_collection import InvestmentCollection, InvestmentCollectionMember
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction
from app.repositories.utils import apply_entry_sort

# Sortable columns for the investments list. `category` is sorted as TEXT rather than as the enum:
# ORDER BY on a Postgres enum follows its DECLARATION order, which differs between a database built
# from 01_create_tables.sql and one built by migrations, so the same rows would come back in a
# different order per environment.
_SORT_COLUMNS = {
    "name": Investment.name,
    "category": cast(Investment.category, String),
    "base_currency": Investment.base_currency,
    "broker": Investment.broker,
}


# Lists investments for a user with optional filters and pagination. Returns (items, total).
async def list_by_user_filtered(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    collection_ids: list[int] | None = None,
    category: InvestmentCategory | None = None,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> tuple[list[Investment], int]:
    stmt = select(Investment).where(Investment.user_id == user_id)
    if active_only:
        stmt = stmt.where(Investment.is_active.is_(True))
    if search:
        stmt = stmt.where(Investment.name.ilike(f"%{search}%"))
    if category:
        stmt = stmt.where(Investment.category == category)
    if collection_ids:
        stmt = stmt.where(
            Investment.id.in_(select(InvestmentCollectionMember.investment_id).where(InvestmentCollectionMember.collection_id.in_(collection_ids)))
        )
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await session.execute(count_stmt)
    total = count_result.scalar_one()
    # This list is paginated, so the sort needs the id tiebreak too: `category` and `base_currency`
    # are low-cardinality, and without a total order Postgres may repeat a row across pages or skip it.
    sorted_stmt = apply_entry_sort(
        stmt,
        Investment,
        sort_by,
        sort_order,
        sort_columns=_SORT_COLUMNS,
        default_order=(Investment.id,),
    )
    items_stmt = sorted_stmt.offset((page - 1) * page_size).limit(page_size)
    items_result = await session.execute(items_stmt)
    items = list(items_result.scalars().all())
    return items, total


# Fetches a single investment by id and user_id. Returns None if not found or not owned.
async def get_by_id(
    session: AsyncSession,
    investment_id: int,
    user_id: int,
) -> Investment | None:
    result = await session.execute(
        select(Investment).where(
            Investment.id == investment_id,
            Investment.user_id == user_id,
        ),
    )
    return result.scalar_one_or_none()


# Returns collections for each investment id as {investment_id: [(collection_id, collection_name)]}.
async def get_collections_by_investment_ids(
    session: AsyncSession,
    investment_ids: list[int],
) -> dict[int, list[tuple[int, str]]]:
    if not investment_ids:
        return {}
    stmt = (
        select(InvestmentCollectionMember.investment_id, InvestmentCollection.id, InvestmentCollection.name)
        .join(InvestmentCollection, InvestmentCollectionMember.collection_id == InvestmentCollection.id)
        .where(InvestmentCollectionMember.investment_id.in_(investment_ids))
        .order_by(InvestmentCollection.id)
    )
    result = await session.execute(stmt)
    collections_map: dict[int, list[tuple[int, str]]] = {}
    for inv_id, collection_id, collection_name in result.all():
        collections_map.setdefault(inv_id, []).append((collection_id, collection_name))
    return collections_map


# Returns investments matching the given IDs owned by the user.
async def get_by_ids(session: AsyncSession, ids: list[int], user_id: int) -> list[Investment]:
    if not ids:
        return []
    result = await session.execute(select(Investment).where(Investment.id.in_(ids), Investment.user_id == user_id))
    return list(result.scalars().all())


# Returns whether the user has any investment (cheap existence check for onboarding; counts
# archived investments too, so archiving a lone holding doesn't un-complete the onboarding step).
async def exists_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Investment.id).where(Investment.user_id == user_id).limit(1))
    return result.first() is not None


# Returns whether the user has any ACTIVE investment. Distinct from exists_by_user, which counts
# archived ones for onboarding: an archived investment contributes nothing to portfolio value, so a
# caller asking "does the net-worth figure have an investment side" has to exclude them.
async def exists_active_by_user(session: AsyncSession, user_id: int) -> bool:
    result = await session.execute(select(Investment.id).where(Investment.user_id == user_id, Investment.is_active.is_(True)).limit(1))
    return result.first() is not None


# Returns all active investments that have a ticker set.
async def list_with_ticker(session: AsyncSession) -> list[Investment]:
    result = await session.execute(
        select(Investment).where(
            Investment.is_active == True,  # noqa: E712
            Investment.ticker.is_not(None),
        )
    )
    return list(result.scalars().all())


# Returns the user's active investments that have a ticker set.
async def list_with_ticker_by_user(session: AsyncSession, user_id: int) -> list[Investment]:
    result = await session.execute(
        select(Investment).where(
            Investment.user_id == user_id,
            Investment.is_active == True,  # noqa: E712
            Investment.ticker.is_not(None),
        )
    )
    return list(result.scalars().all())


# Returns the names of the user's investments (used to flag duplicates on import).
async def list_names_by_user(session: AsyncSession, user_id: int) -> list[str]:
    result = await session.execute(select(Investment.name).where(Investment.user_id == user_id))
    return list(result.scalars().all())


# Returns (id, name, ticker, base_currency) for every investment owned by the user. Powers the
# nested-import resolver (identifier match + row-currency-vs-base validation).
async def list_identifiers_by_user(session: AsyncSession, user_id: int) -> list[tuple[int, str, str | None, str]]:
    result = await session.execute(
        select(Investment.id, Investment.name, Investment.ticker, Investment.base_currency)
        .where(Investment.user_id == user_id)
        .order_by(Investment.id)
    )
    return [(row[0], row[1], row[2], row[3]) for row in result.all()]


# Persists a new investment and flushes to get the id.
async def create(session: AsyncSession, investment: Investment) -> Investment:
    session.add(investment)
    await session.flush()
    return investment


# Bulk-inserts new investments and flushes to assign ids. Returns the inserted investments.
async def bulk_create(session: AsyncSession, investments: list[Investment]) -> list[Investment]:
    if not investments:
        return []
    session.add_all(investments)
    await session.flush()
    return investments


# Persists changes to an existing investment.
async def save(session: AsyncSession, investment: Investment) -> None:
    session.add(investment)


# Re-points every investment a pot holds to one user as private, returning how many moved. Called only
# from account deletion, when the leaving account holds the group's last active linked seat: at that
# moment nobody can ever see the pot again, so the honest outcome is that the holdings were always
# this user's. Runs BEFORE the account row goes — afterwards there is no user id left to assign.
async def reassign_pot_to_user(session: AsyncSession, pot_id: int, user_id: int) -> int:
    result = await session.execute(
        sa_update(Investment).where(Investment.pot_id == pot_id).values(user_id=user_id, pot_id=None).execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


# Moves investments between scopes, returning how many moved. `pot_id=None` moves them back to the
# caller as private, which is the only direction that needs a user id.
#
# The RLS-denormalized children are re-pointed in the SAME statement set, and that is not tidiness:
# investment_snapshots and transactions carry a copy of their parent's scope precisely so their policies do not
# have to join back to it, so a parent whose children still name the old scope is a row its own
# history has become invisible to. They are updated by PARENT id rather than by their own old scope,
# so a child that had somehow drifted is corrected rather than left behind.
async def move_to_scope(session: AsyncSession, ids: list[int], *, pot_id: int | None, user_id: int | None) -> int:
    if not ids:
        return 0
    values = {"pot_id": pot_id, "user_id": user_id}
    result = await session.execute(sa_update(Investment).where(Investment.id.in_(ids)).values(**values).execution_options(synchronize_session=False))
    await session.execute(
        sa_update(InvestmentSnapshot).where(InvestmentSnapshot.investment_id.in_(ids)).values(**values).execution_options(synchronize_session=False)
    )
    await session.execute(
        sa_update(Transaction).where(Transaction.investment_id.in_(ids)).values(**values).execution_options(synchronize_session=False)
    )
    return int(result.rowcount or 0)


# Get a single investment by id WITHOUT pre-filtering by owner, for callers that must reach a
# co-owned one (whose user_id is NULL, so get_by_id can never match it). RLS decides what is
# reachable at all; the caller decides which scope it needed.
async def get_by_id_any_scope(session: AsyncSession, investment_id: int) -> Investment | None:
    result = await session.execute(select(Investment).where(Investment.id == investment_id))
    return result.scalar_one_or_none()


# Batch sibling of get_by_ids that does NOT pre-filter by owner, for callers that must reach co-owned
# rows (whose user_id is NULL, so the owner-filtered version can never match one). RLS still decides
# what is reachable; the caller checks which scope it actually needed.
async def get_by_ids_any_scope(session: AsyncSession, ids: list[int]) -> list[Investment]:
    if not ids:
        return []
    result = await session.execute(select(Investment).where(Investment.id.in_(ids)))
    return list(result.scalars().all())


# Namespace to call repository functions (e.g. investment_repository.list_by_user_filtered).
class InvestmentRepository:
    bulk_create = staticmethod(bulk_create)
    create = staticmethod(create)
    exists_active_by_user = staticmethod(exists_active_by_user)
    exists_by_user = staticmethod(exists_by_user)
    get_by_id = staticmethod(get_by_id)
    get_by_id_any_scope = staticmethod(get_by_id_any_scope)
    get_by_ids = staticmethod(get_by_ids)
    get_by_ids_any_scope = staticmethod(get_by_ids_any_scope)
    get_collections_by_investment_ids = staticmethod(get_collections_by_investment_ids)
    list_by_user_filtered = staticmethod(list_by_user_filtered)
    list_identifiers_by_user = staticmethod(list_identifiers_by_user)
    list_names_by_user = staticmethod(list_names_by_user)
    list_with_ticker = staticmethod(list_with_ticker)
    list_with_ticker_by_user = staticmethod(list_with_ticker_by_user)
    move_to_scope = staticmethod(move_to_scope)
    reassign_pot_to_user = staticmethod(reassign_pot_to_user)
    save = staticmethod(save)


# Singleton used by services to access investment persistence.
investment_repository = InvestmentRepository()
