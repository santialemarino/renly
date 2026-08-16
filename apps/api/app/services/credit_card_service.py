from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CardBucketBalance, HasLinkedExpensesError, NotFoundError
from app.models.account import Account
from app.models.card_settlement import CardSettlement
from app.models.credit_card import CreditCard
from app.models.user import User
from app.repositories import (
    account_repository,
    card_settlement_repository,
    credit_card_repository,
    expense_repository,
    installment_repository,
    payment_obligation_repository,
    subscription_repository,
)
from app.schemas.card_settlement import CardSettlementResponse
from app.services import account_service, card_reconciliation_service

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
    user_id: int,
) -> dict[int, list[CardBucketBalance]]:
    if not card_ids:
        return {}
    expense_grouped = await expense_repository.sum_by_credit_card_ids_grouped(session, card_ids, user_id)
    settlement_grouped = await card_settlement_repository.sum_by_card_ids_grouped(session, card_ids)
    return compute_card_balances(card_ids, card_currencies, expense_grouped, settlement_grouped)


# Returns {card_id: has-at-least-one-linked-expense} for the given cards in one batch query.
async def cards_have_expenses(session: AsyncSession, card_ids: list[int], user_id: int) -> dict[int, bool]:
    counts = await expense_repository.count_by_credit_card_ids(session, card_ids, user_id)
    return {card_id: counts.get(card_id, 0) > 0 for card_id in card_ids}


# Create a new credit card. A default funding account must be owned and denominated in the card's own
# currency — the settlement dialog filters the picker to the settled bucket's currency, so a default in
# any other currency could only ever be a link that dialog would refuse.
async def create_card(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    closing_day: int,
    due_day: int,
    currency: str,
    monthly_payment: Decimal | None = None,
    default_account_id: int | None = None,
) -> CreditCard:
    await account_service.validate_account_link(session, user, default_account_id, currency)
    card = CreditCard(
        user_id=user.id,
        name=name,
        closing_day=closing_day,
        due_day=due_day,
        currency=currency,
        monthly_payment=monthly_payment,
        default_account_id=default_account_id,
    )
    card = await credit_card_repository.create(session, card)
    await session.commit()
    return card


# Update an existing credit card. Only provided fields are changed. The default funding account is
# re-validated against the EFFECTIVE currency (request field over the stored row), so changing the
# card's currency while a default is set is refused rather than silently leaving a mismatched pair.
# Only re-validated when that pair actually MOVES: an unchanged pair was already validated when it was
# attached, and re-checking it would let a stale stored default (its account's currency changed while
# nothing else referenced it) block an unrelated edit such as a rename.
async def update_card(
    session: AsyncSession,
    card_id: int,
    user: User,
    **fields: object,
) -> CreditCard:
    card = await get_card(session, card_id, user)
    await account_service.validate_effective_default_link(
        session, user, fields=fields, stored_account_id=card.default_account_id, stored_currency=card.currency
    )
    for key, value in fields.items():
        setattr(card, key, value)
    await credit_card_repository.save(session, card)
    await session.commit()
    await session.refresh(card)
    return card


# Delete a credit card. Rejects with 409 when any expense or plan still references the card,
# naming the blocking entity kinds so the user knows what to detach or archive first.
async def delete_card(session: AsyncSession, card_id: int, user: User) -> None:
    card = await get_card(session, card_id, user)
    references = (
        ("expenses", await expense_repository.count_by_credit_card(session, card_id, user.id)),
        ("subscriptions", await subscription_repository.count_by_credit_card(session, card_id, user.id)),
        ("installment plans", await installment_repository.count_by_credit_card(session, card_id, user.id)),
        ("payment obligations", await payment_obligation_repository.count_by_credit_card(session, card_id, user.id)),
    )
    linked = [noun for noun, count in references if count > 0]
    if linked:
        raise HasLinkedExpensesError(f"Cannot delete a credit card that has linked {', '.join(linked)}. Archive it instead.")
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


# Maps a settlement to its response, denormalizing the funding account's name so a client renders which
# account paid without a second lookup — and so an archived account still reads by name.
def _to_settlement_response(settlement: CardSettlement, account: Account | None) -> CardSettlementResponse:
    resp = CardSettlementResponse.model_validate(settlement)
    resp.account_name = account.name if account is not None else None
    return resp


# List settlements for a credit card (verifies card ownership first), each carrying its funding
# account's name. Accounts are batch-loaded once for the whole list rather than per row.
async def list_settlements(session: AsyncSession, card_id: int, user: User) -> list[CardSettlementResponse]:
    await get_card(session, card_id, user)
    settlements = await card_settlement_repository.list_by_card(session, card_id)
    referenced = sorted({s.account_id for s in settlements if s.account_id is not None})
    accounts = {a.id: a for a in await account_repository.get_by_ids(session, referenced, user.id) if a.id is not None}
    return [_to_settlement_response(s, accounts.get(s.account_id) if s.account_id is not None else None) for s in settlements]


# Record a new card settlement. Marks any reconciliation covering the settlement date stale (Phase 3, Step 5).
async def create_settlement(
    session: AsyncSession,
    card_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    account_id: int | None = None,
    notes: str | None = None,
) -> CardSettlementResponse:
    await get_card(session, card_id, user)
    account = await account_service.validate_account_link(session, user, account_id, currency)
    settlement = CardSettlement(
        credit_card_id=card_id,
        user_id=user.id,
        date=date,
        amount=amount,
        currency=currency,
        account_id=account_id,
        notes=notes,
    )
    settlement = await card_settlement_repository.create(session, settlement)
    await card_reconciliation_service.mark_stale_for_date(session, card_id, currency, date)
    await session.commit()
    return _to_settlement_response(settlement, account)


# Delete a settlement (verifies card ownership first). Marks any reconciliation covering the settlement date stale.
async def delete_settlement(session: AsyncSession, card_id: int, settlement_id: int, user: User) -> None:
    await get_card(session, card_id, user)
    settlement = await card_settlement_repository.get_by_id(session, settlement_id, card_id)
    if settlement is None:
        raise NotFoundError("Settlement not found.")
    old_currency = settlement.currency
    old_date = settlement.date
    await card_settlement_repository.delete(session, settlement)
    await card_reconciliation_service.mark_stale_for_date(session, card_id, old_currency, old_date)
    await session.commit()
