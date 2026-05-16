from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CardBucketBalance, HasLinkedExpensesError, NotFoundError
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.user import User
from app.repositories import card_settlement_repository, credit_card_repository, expense_repository

# --- Credit cards ---


# List credit cards for a user with optional search, sorting, and archive filtering.
async def list_cards(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[CreditCard]:
    return await credit_card_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single credit card by id. Raises NotFoundError if not found.
async def get_card(session: AsyncSession, card_id: int, user: User) -> CreditCard:
    card = await credit_card_repository.get_by_id(session, card_id, user.id)
    if card is None:
        raise NotFoundError("Credit card not found.")
    return card


# Pure computation: returns one CardBucketBalance per currency that has activity
# on a card. Each bucket's balance is sum(expenses) - sum(settlements) in that
# currency — no cross-currency conversion. The card's primary currency always
# appears even with zero activity so newly-created cards still surface a bucket.
# Buckets are ordered primary first, then remaining currencies alphabetically.
def compute_card_balances(
    card_ids: list[int],
    card_currencies: dict[int, str],
    expense_grouped: dict[int, dict[str, float]],
    settlement_grouped: dict[int, dict[str, float]],
) -> dict[int, list[CardBucketBalance]]:
    result: dict[int, list[CardBucketBalance]] = {}
    for card_id in card_ids:
        primary = card_currencies.get(card_id)
        expense_by_cur = expense_grouped.get(card_id, {})
        settlement_by_cur = settlement_grouped.get(card_id, {})
        active = set(expense_by_cur) | set(settlement_by_cur)
        if primary:
            active.add(primary)
        ordered = ([primary] if primary else []) + sorted(c for c in active if c != primary)
        buckets: list[CardBucketBalance] = []
        for cur in ordered:
            expenses = Decimal(str(expense_by_cur.get(cur, 0)))
            settlements = Decimal(str(settlement_by_cur.get(cur, 0)))
            buckets.append(CardBucketBalance(currency=cur, balance=expenses - settlements))
        result[card_id] = buckets
    return result


# Returns per-bucket balances for the given cards. {card_id: [CardBucketBalance, ...]}.
async def get_card_balances(
    session: AsyncSession,
    card_ids: list[int],
    card_currencies: dict[int, str],
) -> dict[int, list[CardBucketBalance]]:
    if not card_ids:
        return {}
    expense_grouped = await expense_repository.sum_by_credit_card_ids_grouped(session, card_ids)
    settlement_grouped = await card_settlement_repository.sum_by_card_ids_grouped(session, card_ids)
    return compute_card_balances(card_ids, card_currencies, expense_grouped, settlement_grouped)


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


# Delete a credit card. Rejects if the card has linked expenses (409).
async def delete_card(session: AsyncSession, card_id: int, user: User) -> None:
    card = await get_card(session, card_id, user)
    expense_count = await expense_repository.count_by_credit_card(session, card_id)
    if expense_count > 0:
        raise HasLinkedExpensesError()
    await credit_card_repository.delete(session, card)
    await session.commit()


# Archive a credit card (set is_active = false).
async def archive_card(session: AsyncSession, card_id: int, user: User) -> CreditCard:
    card = await get_card(session, card_id, user)
    card.is_active = False
    await credit_card_repository.save(session, card)
    await session.commit()
    await session.refresh(card)
    return card


# Unarchive a credit card (set is_active = true).
async def unarchive_card(session: AsyncSession, card_id: int, user: User) -> CreditCard:
    card = await get_card(session, card_id, user)
    card.is_active = True
    await credit_card_repository.save(session, card)
    await session.commit()
    await session.refresh(card)
    return card


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
