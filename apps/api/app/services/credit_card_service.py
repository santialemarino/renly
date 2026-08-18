from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    CardBucketBalance,
    HasLinkedExpensesError,
    NotFoundError,
    SettlementAccountAmountRequiredError,
    SettlementAccountAmountWithoutAccountError,
    SettlementAmountsMustMatchError,
    SettlementBeforeAccountOpenedError,
)
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


# Create a new credit card. A default funding account must be owned but may name ANY currency: a
# settlement can now pay a bucket from an account denominated differently, recording what left that
# account, so a peso account funding a USD card — the most common Argentine arrangement — is exactly the
# case the default exists for. Only ownership is checked (a plan's default still must match, because a
# plan's charge has no second amount to record).
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
    await account_service.load_linked_account(session, user, default_account_id)
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


# Update an existing credit card. Only provided fields are changed. A newly-named default funding account
# is checked for ownership only — its currency is free, so changing the card's currency can no longer
# invalidate the default and nothing has to be re-validated against the merged pair. Validated only when
# the account actually MOVES, so an unrelated edit (a rename, an archive) never re-touches a stored
# default; `fields.get` falls back to the stored id so absence means "unchanged", not "clear".
async def update_card(
    session: AsyncSession,
    card_id: int,
    user: User,
    **fields: object,
) -> CreditCard:
    card = await get_card(session, card_id, user)
    new_account_id = fields.get("default_account_id", card.default_account_id)
    if new_account_id != card.default_account_id:
        await account_service.load_linked_account(session, user, new_account_id)
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


# Maps a settlement to its response, denormalizing the funding account's name and currency so a client
# renders which account paid, and in what denomination, without a second lookup — and so an archived
# account still reads by name. The currency is what lets a client tell a cross-currency row apart
# without comparing against its own accounts list, which can fail to load.
def _to_settlement_response(settlement: CardSettlement, account: Account | None) -> CardSettlementResponse:
    resp = CardSettlementResponse.model_validate(settlement)
    resp.account_name = account.name if account is not None else None
    resp.account_currency = account.currency if account is not None else None
    return resp


# Resolves the cash leg of a settlement, returning what to STORE in account_amount. None means "no
# conversion happened", which is what keeps every pre-existing row correct and lets the cash sums read
# coalesce(account_amount, amount).
#
# Mirrors transfer_service._resolve_to_amount, and for the same reason in both directions: across
# currencies only the user knows the blended rate the bank charged (the "dólar tarjeta" already contains
# the ~30% perception, so it is never a clean multiple of anything Renly can look up), while within one
# currency no conversion happened at all, so the account must be debited exactly what came off the
# bucket. A redundant-but-equal amount normalizes to None rather than being stored twice, so
# "account_amount IS NOT NULL" always means "these currencies differ".
# Rejects a settlement dated before the funding account existed. Every cash sum is bounded below by that
# account's opening_date, so the cash leg would be dropped while the card leg still cleared the bucket —
# a settlement that reduces debt and moves no money. Mirrors transfer_service._ensure_both_accounts_open;
# an UNLINKED settlement has no account to be open, so there is nothing to check.
def _ensure_account_open(account: Account | None, date: date_type) -> None:
    if account is not None and date < account.opening_date:
        raise SettlementBeforeAccountOpenedError(account.opening_date)


def _resolve_account_amount(account: Account | None, currency: str, amount: Decimal, account_amount: Decimal | None) -> Decimal | None:
    if account is None:
        if account_amount is not None:
            raise SettlementAccountAmountWithoutAccountError()
        return None
    if account.currency == currency:
        if account_amount is not None and account_amount != amount:
            raise SettlementAmountsMustMatchError()
        return None
    if account_amount is None:
        raise SettlementAccountAmountRequiredError(currency, account.currency)
    return account_amount


# List settlements for a credit card (verifies card ownership first), each carrying its funding
# account's name. Accounts are batch-loaded once for the whole list rather than per row.
async def list_settlements(session: AsyncSession, card_id: int, user: User) -> list[CardSettlementResponse]:
    await get_card(session, card_id, user)
    settlements = await card_settlement_repository.list_by_card(session, card_id)
    referenced = sorted({s.account_id for s in settlements if s.account_id is not None})
    accounts = {a.id: a for a in await account_repository.get_by_ids(session, referenced, user.id) if a.id is not None}
    return [_to_settlement_response(s, accounts.get(s.account_id) if s.account_id is not None else None) for s in settlements]


# Record a new card settlement. The funding account may be denominated differently from the bucket being
# cleared, in which case account_amount records what actually left it. Marks any reconciliation covering
# the settlement date stale (Phase 3, Step 5) — keyed on the CARD leg's currency, which is what moves the
# bucket a reconciliation reconciles.
async def create_settlement(
    session: AsyncSession,
    card_id: int,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    account_id: int | None = None,
    account_amount: Decimal | None = None,
    notes: str | None = None,
) -> CardSettlementResponse:
    await get_card(session, card_id, user)
    account = await account_service.load_linked_account(session, user, account_id)
    _ensure_account_open(account, date)
    resolved_account_amount = _resolve_account_amount(account, currency, amount, account_amount)
    settlement = CardSettlement(
        credit_card_id=card_id,
        user_id=user.id,
        date=date,
        amount=amount,
        currency=currency,
        account_id=account_id,
        account_amount=resolved_account_amount,
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
