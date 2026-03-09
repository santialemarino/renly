from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.investment import Currency, Investment, InvestmentCategory
from app.models.user import User
from app.repositories import investment_repository


# Lists investments for the user. Returns only active by default.
async def list_investments(
    session: AsyncSession,
    user: User,
    *,
    active_only: bool = True,
) -> list[Investment]:
    return await investment_repository.list_by_user(session, user.id, active_only=active_only)


# Fetches one investment by id. Raises 404 if not found or not owned by user.
async def get_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> Investment:
    inv = await investment_repository.get_by_id(session, investment_id, user.id)
    if inv is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Investment not found",
        )
    return inv


# Creates a new investment for the user.
async def create_investment(
    session: AsyncSession,
    user: User,
    name: str,
    category: InvestmentCategory,
    base_currency: Currency,
    broker: str | None = None,
    notes: str | None = None,
) -> Investment:
    investment = Investment(
        user_id=user.id,
        name=name,
        category=category,
        base_currency=base_currency,
        broker=broker,
        notes=notes,
    )
    return await investment_repository.create(session, investment)


# Updates an existing investment. Only provided fields are updated. Returns updated investment.
async def update_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
    *,
    name: str | None = None,
    category: InvestmentCategory | None = None,
    base_currency: Currency | None = None,
    broker: str | None = None,
    notes: str | None = None,
    is_active: bool | None = None,
) -> Investment:
    inv = await get_investment(session, investment_id, user)
    if name is not None:
        inv.name = name
    if category is not None:
        inv.category = category
    if base_currency is not None:
        inv.base_currency = base_currency
    if broker is not None:
        inv.broker = broker
    if notes is not None:
        inv.notes = notes
    if is_active is not None:
        inv.is_active = is_active
    await investment_repository.save(session, inv)
    await session.refresh(inv)
    return inv


# Soft-deletes an investment (sets is_active = False).
async def delete_investment(
    session: AsyncSession,
    investment_id: int,
    user: User,
) -> None:
    await update_investment(session, investment_id, user, is_active=False)
