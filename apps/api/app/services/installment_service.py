from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.installment import Installment
from app.models.user import User
from app.repositories import installment_repository


# List installments for a user with optional search, sorting, and archive filtering.
async def list_installments(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Installment]:
    return await installment_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single installment by id. Raises NotFoundError if not found.
async def get_installment(session: AsyncSession, installment_id: int, user: User) -> Installment:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        raise NotFoundError("Installment not found.")
    return installment


# Create a new installment plan.
async def create_installment(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    total_amount: Decimal,
    installment_amount: Decimal,
    currency: str,
    installments_count: int,
    start_date: date_type,
    current_installment: int = 1,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
) -> Installment:
    installment = Installment(
        user_id=user.id,
        name=name,
        total_amount=total_amount,
        installment_amount=installment_amount,
        currency=currency,
        installments_count=installments_count,
        current_installment=current_installment,
        start_date=start_date,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
    )
    installment = await installment_repository.create(session, installment)
    await session.commit()
    return installment


# Update an existing installment plan. Only provided fields are changed.
async def update_installment(
    session: AsyncSession,
    installment_id: int,
    user: User,
    **fields: object,
) -> Installment:
    installment = await get_installment(session, installment_id, user)
    for key, value in fields.items():
        setattr(installment, key, value)
    await installment_repository.save(session, installment)
    await session.commit()
    await session.refresh(installment)
    return installment


# Delete an installment plan.
async def delete_installment(session: AsyncSession, installment_id: int, user: User) -> None:
    installment = await get_installment(session, installment_id, user)
    await installment_repository.delete(session, installment)
    await session.commit()
