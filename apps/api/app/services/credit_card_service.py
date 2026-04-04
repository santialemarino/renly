from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.user import User
from app.repositories import card_settlement_repository, credit_card_repository, expense_repository

# --- Credit cards ---


# List credit cards for a user with optional search and sorting.
async def list_cards(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
) -> list[CreditCard]:
    return await credit_card_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
    )


# Get a single credit card by id. Raises NotFoundError if not found.
async def get_card(session: AsyncSession, card_id: int, user: User) -> CreditCard:
    card = await credit_card_repository.get_by_id(session, card_id, user.id)
    if card is None:
        raise NotFoundError("Credit card not found.")
    return card


# Compute the current balance for a credit card (expenses - settlements).
async def get_card_balance(session: AsyncSession, card_id: int) -> Decimal:
    total_expenses = await expense_repository.sum_by_credit_card(session, card_id)
    total_settlements = await card_settlement_repository.sum_by_card(session, card_id)
    return Decimal(str(total_expenses)) - Decimal(str(total_settlements))


# Compute balances for multiple cards in two batch queries. Returns {card_id: balance}.
async def get_card_balances(session: AsyncSession, card_ids: list[int]) -> dict[int, Decimal]:
    if not card_ids:
        return {}
    expense_sums = await expense_repository.sum_by_credit_card_ids(session, card_ids)
    settlement_sums = await card_settlement_repository.sum_by_card_ids(session, card_ids)
    return {card_id: Decimal(str(expense_sums.get(card_id, 0))) - Decimal(str(settlement_sums.get(card_id, 0))) for card_id in card_ids}


# Create a new credit card.
async def create_card(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    closing_day: int,
    due_day: int,
    currency: str,
) -> CreditCard:
    card = CreditCard(
        user_id=user.id,
        name=name,
        closing_day=closing_day,
        due_day=due_day,
        currency=currency,
    )
    card = await credit_card_repository.create(session, card)
    await session.commit()
    return card


# Update an existing credit card. Only provided fields are changed.
async def update_card(
    session: AsyncSession,
    card_id: int,
    user: User,
    **fields: object,
) -> CreditCard:
    card = await get_card(session, card_id, user)
    for key, value in fields.items():
        setattr(card, key, value)
    await credit_card_repository.save(session, card)
    await session.commit()
    await session.refresh(card)
    return card


# Delete a credit card.
async def delete_card(session: AsyncSession, card_id: int, user: User) -> None:
    card = await get_card(session, card_id, user)
    await credit_card_repository.delete(session, card)
    await session.commit()


# --- Settlements ---


# List settlements for a credit card (verifies card ownership first).
async def list_settlements(session: AsyncSession, card_id: int, user: User) -> list[CardSettlement]:
    await get_card(session, card_id, user)
    return await card_settlement_repository.list_by_card(session, card_id)


# Record a new card settlement.
async def create_settlement(
    session: AsyncSession,
    card_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    notes: str | None = None,
) -> CardSettlement:
    await get_card(session, card_id, user)
    settlement = CardSettlement(
        credit_card_id=card_id,
        date=date,
        amount=amount,
        currency=currency,
        notes=notes,
    )
    settlement = await card_settlement_repository.create(session, settlement)
    await session.commit()
    return settlement


# Delete a settlement (verifies card ownership first).
async def delete_settlement(session: AsyncSession, card_id: int, settlement_id: int, user: User) -> None:
    await get_card(session, card_id, user)
    settlement = await card_settlement_repository.get_by_id(session, settlement_id, card_id)
    if settlement is None:
        raise NotFoundError("Settlement not found.")
    await card_settlement_repository.delete(session, settlement)
    await session.commit()
