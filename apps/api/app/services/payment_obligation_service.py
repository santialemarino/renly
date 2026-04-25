from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.payment_obligation import PaymentObligation
from app.models.user import User
from app.repositories import payment_obligation_repository


# List payment obligations for a user with optional search, sorting, and archive filtering.
async def list_obligations(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[PaymentObligation]:
    return await payment_obligation_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single payment obligation by id. Raises NotFoundError if not found.
async def get_obligation(session: AsyncSession, obligation_id: int, user: User) -> PaymentObligation:
    obligation = await payment_obligation_repository.get_by_id(session, obligation_id, user.id)
    if obligation is None:
        raise NotFoundError("Payment obligation not found.")
    return obligation


# Create a new payment obligation.
async def create_obligation(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    amount: Decimal,
    currency: str,
    due_date: date_type,
    recurrence: str | None = None,
    category: str | None = None,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
    notes: str | None = None,
) -> PaymentObligation:
    obligation = PaymentObligation(
        user_id=user.id,
        name=name,
        amount=amount,
        currency=currency,
        due_date=due_date,
        recurrence=recurrence,
        category=category,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        notes=notes,
    )
    obligation = await payment_obligation_repository.create(session, obligation)
    await session.commit()
    return obligation


# Update an existing payment obligation. Only provided fields are changed.
async def update_obligation(
    session: AsyncSession,
    obligation_id: int,
    user: User,
    **fields: object,
) -> PaymentObligation:
    obligation = await get_obligation(session, obligation_id, user)
    for key, value in fields.items():
        setattr(obligation, key, value)
    await payment_obligation_repository.save(session, obligation)
    await session.commit()
    await session.refresh(obligation)
    return obligation


# Delete a payment obligation.
async def delete_obligation(session: AsyncSession, obligation_id: int, user: User) -> None:
    obligation = await get_obligation(session, obligation_id, user)
    await payment_obligation_repository.delete(session, obligation)
    await session.commit()
