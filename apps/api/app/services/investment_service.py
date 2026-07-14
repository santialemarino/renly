from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CurrencyChangeBlockedError, InvestmentCurrencyMismatchError, NotFoundError
from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.snapshot import InvestmentSnapshot
from app.models.transaction import Transaction, TransactionType
from app.models.user import User
from app.repositories import (
    group_repository,
    investment_repository,
    snapshot_repository,
    transaction_repository,
)
from app.schemas.investment import InvestmentGroupInfo, InvestmentListResponse, InvestmentResponse
from app.services import settings_service


# Assembles InvestmentResponse, enriching it with group info and snapshot presence.
def _build_response(
    inv: Investment,
    groups_map: dict[int, list[tuple[int, str]]],
    snapshots_set: set[int],
) -> InvestmentResponse:
    groups = [InvestmentGroupInfo(id=gid, name=gname) for gid, gname in groups_map.get(inv.id or 0, [])]
    return InvestmentResponse(
        id=inv.id or 0,
        name=inv.name,
        category=inv.category,
        base_currency=inv.base_currency,
        ticker=inv.ticker,
        broker=inv.broker,
        notes=inv.notes,
        is_active=inv.is_active,
        has_snapshots=(inv.id or 0) in snapshots_set,
        created_at=inv.created_at,
        updated_at=inv.updated_at,
        groups=groups,
    )


# Lists investments for the user with filters and pagination. Returns InvestmentListResponse.
async def list_investments(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    group_ids: list[int] | None = None,
    category: InvestmentCategory | None = None,
    active_only: bool = True,
    page: int = 1,
    page_size: int = 20,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> InvestmentListResponse:
    items, total = await investment_repository.list_by_user_filtered(
        session,
        user.id,
        search=search,
        group_ids=group_ids,
        category=category,
        active_only=active_only,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    inv_ids = [inv.id for inv in items if inv.id is not None]
    groups_map = await investment_repository.get_groups_by_investment_ids(session, inv_ids)
    snapshots_set = await snapshot_repository.get_ids_with_snapshots(session, inv_ids)
    return InvestmentListResponse(
        items=[_build_response(inv, groups_map, snapshots_set) for inv in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# Fetches one investment by id. Raises NotFoundError if not found or not owned by user.
async def get_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> Investment:
    inv = await investment_repository.get_by_id(session, investment_id, user.id)
    if inv is None:
        raise NotFoundError("Investment not found")
    return inv


# Creates a new investment for the user.
async def create_investment(
    session: AsyncSession,
    user: User,
    name: str,
    category: InvestmentCategory,
    base_currency: str,
    ticker: str | None = None,
    broker: str | None = None,
    notes: str | None = None,
) -> Investment:
    investment = Investment(
        user_id=user.id,
        name=name,
        category=category,
        base_currency=base_currency,
        ticker=ticker,
        broker=broker,
        notes=notes,
    )
    investment = await investment_repository.create(session, investment)
    # Retire the investments first-run sample once the user has their first investment.
    await settings_service.retire_sample(session, user.id, "investments")
    await session.commit()
    return investment


# Updates an existing investment. Only provided fields are updated. Returns updated investment.
async def update_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
    *,
    name: str | None = None,
    category: InvestmentCategory | None = None,
    base_currency: str | None = None,
    ticker: str | None = None,
    broker: str | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> Investment:
    inv = await get_investment(session, investment_id, user)
    # Prevent currency change when snapshots exist — would corrupt stored values.
    if base_currency is not None and base_currency != inv.base_currency:
        if await snapshot_repository.has_snapshots(session, investment_id):
            raise CurrencyChangeBlockedError()
    if name is not None:
        inv.name = name
    if category is not None:
        inv.category = category
    if base_currency is not None:
        inv.base_currency = base_currency
    if ticker is not None:
        inv.ticker = ticker
    if broker is not None:
        inv.broker = broker
    if notes is not None:
        inv.notes = notes
    if is_active is not None:
        inv.is_active = is_active
    await investment_repository.save(session, inv)
    await session.commit()
    await session.refresh(inv)
    return inv


# Archives an investment (sets is_active = False).
async def archive_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> None:
    await update_investment(session, investment_id, user, is_active=False)


# Unarchives an investment (sets is_active = True).
async def unarchive_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> None:
    await update_investment(session, investment_id, user, is_active=True)


# Sets which groups this investment belongs to. Validates group ownership. Raises NotFoundError.
async def set_investment_groups(
    session: AsyncSession,
    investment_id: int,
    user: User,
    group_ids: list[int],
) -> None:
    await get_investment(session, investment_id, user)
    if group_ids:
        user_groups = await group_repository.list_by_user(session, user.id)
        user_group_ids = {g.id for g in user_groups}
        invalid = set(group_ids) - user_group_ids
        if invalid:
            raise NotFoundError(f"Groups not found: {sorted(invalid)}")
    await group_repository.set_groups_for_investment(session, investment_id, group_ids)
    await session.commit()


# Returns True if the investment has at least one snapshot.
async def has_snapshots(session: AsyncSession, investment_id: int) -> bool:
    return await snapshot_repository.has_snapshots(session, investment_id)


# Lists snapshots for an investment. Raises 404 if investment not found or not owned.
async def list_snapshots(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> list[InvestmentSnapshot]:
    await get_investment(session, investment_id, user)
    return await snapshot_repository.list_by_investment(session, investment_id)


# Creates or updates a snapshot for the given investment and date. One per (investment, date).
async def upsert_snapshot(
    session: AsyncSession,
    investment_id: int,
    user: User,
    *,
    snapshot_date: date,
    value: Decimal,
    quantity: Decimal | None = None,
    currency: Currency,
    notes: str | None = None,
) -> InvestmentSnapshot:
    inv = await get_investment(session, investment_id, user)
    # A snapshot valued in a different currency than the investment's base corrupts every
    # metric downstream — reject instead of silently storing (fail-loud, no auto-convert).
    if currency != inv.base_currency:
        raise InvestmentCurrencyMismatchError(str(currency), str(inv.base_currency))
    existing = await snapshot_repository.get_by_investment_and_date(session, investment_id, snapshot_date)
    if existing is not None:
        existing.value = value
        existing.quantity = quantity
        existing.currency = currency
        existing.notes = notes
        await snapshot_repository.save(session, existing)
        await session.commit()
        await session.refresh(existing)
        return existing
    snapshot = InvestmentSnapshot(
        investment_id=investment_id,
        user_id=user.id,
        date=snapshot_date,
        value=value,
        quantity=quantity,
        currency=currency,
        notes=notes,
    )
    snapshot = await snapshot_repository.create(session, snapshot)
    await session.commit()
    return snapshot


# Lists transactions for an investment. Raises 404 if investment not found or not owned.
async def list_transactions(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> list[Transaction]:
    await get_investment(session, investment_id, user)
    return await transaction_repository.list_by_investment(session, investment_id)


# Fetches one transaction by id. Raises NotFoundError if investment/transaction not found/owned.
async def get_transaction(
    session: AsyncSession,
    investment_id: int,
    transaction_id: int,
    user: User,
) -> Transaction:
    await get_investment(session, investment_id, user)
    tx = await transaction_repository.get_by_id(session, transaction_id)
    if tx is None or tx.investment_id != investment_id:
        raise NotFoundError("Transaction not found")
    return tx


# Creates a new transaction for the investment.
async def create_transaction(
    session: AsyncSession,
    investment_id: int,
    user: User,
    *,
    transaction_date: date,
    amount: Decimal,
    quantity: Decimal | None = None,
    currency: Currency,
    tx_type: TransactionType,
    notes: str | None = None,
) -> Transaction:
    inv = await get_investment(session, investment_id, user)
    # A transaction valued in a currency other than the investment's base corrupts every
    # metric downstream — reject instead of silently storing (fail-loud, no auto-convert).
    if currency != inv.base_currency:
        raise InvestmentCurrencyMismatchError(str(currency), str(inv.base_currency))
    transaction = Transaction(
        investment_id=investment_id,
        user_id=user.id,
        date=transaction_date,
        amount=amount,
        quantity=quantity,
        currency=currency,
        type=tx_type,
        notes=notes,
    )
    transaction = await transaction_repository.create(session, transaction)
    await session.commit()
    return transaction


# Updates an existing transaction. Only provided fields are updated. Returns updated transaction.
async def update_transaction(
    session: AsyncSession,
    investment_id: int,
    transaction_id: int,
    user: User,
    *,
    transaction_date: date | None = None,
    amount: Decimal | None = None,
    quantity: Decimal | None = None,
    currency: Currency | None = None,
    tx_type: TransactionType | None = None,
    notes: str | None = None,
) -> Transaction:
    tx = await get_transaction(session, investment_id, transaction_id, user)
    if currency is not None:
        inv = await get_investment(session, investment_id, user)
        if currency != inv.base_currency:
            raise InvestmentCurrencyMismatchError(str(currency), str(inv.base_currency))
    if transaction_date is not None:
        tx.date = transaction_date
    if amount is not None:
        tx.amount = amount
    if quantity is not None:
        tx.quantity = quantity
    if currency is not None:
        tx.currency = currency
    if tx_type is not None:
        tx.type = tx_type
    if notes is not None:
        tx.notes = notes
    await transaction_repository.save(session, tx)
    await session.commit()
    await session.refresh(tx)
    return tx


# Deletes a transaction.
async def delete_transaction(
    session: AsyncSession,
    investment_id: int,
    transaction_id: int,
    user: User,
) -> None:
    tx = await get_transaction(session, investment_id, transaction_id, user)
    await transaction_repository.delete(session, tx)
    await session.commit()
