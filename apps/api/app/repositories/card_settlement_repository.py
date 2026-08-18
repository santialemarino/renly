from datetime import date as date_type
from decimal import Decimal

from sqlalchemy import func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.account import Account
from app.models.card_settlement import CardSettlement


# What the FUNDING ACCOUNT paid, which is only the same thing as what cleared the card when no conversion
# happened. THE one definition, because THREE queries are cash-side and must all agree: the two sums in
# this module plus the per-account ledger's settlement branch, which lives in account_movement_repository
# and imports this rather than re-spelling it. Public for that importer's sake. The card-side sums
# deliberately use CardSettlement.amount directly, and keeping the two spellings visibly different is
# what makes a mistake in either one legible.
def settlement_cash_leg():
    return func.coalesce(CardSettlement.account_amount, CardSettlement.amount)


# List all settlements for a credit card.
async def list_by_card(session: AsyncSession, credit_card_id: int) -> list[CardSettlement]:
    result = await session.execute(
        select(CardSettlement).where(CardSettlement.credit_card_id == credit_card_id).order_by(CardSettlement.date.desc(), CardSettlement.id.desc())
    )
    return list(result.scalars().all())


# Get a single settlement by id and card.
async def get_by_id(session: AsyncSession, settlement_id: int, credit_card_id: int) -> CardSettlement | None:
    result = await session.execute(
        select(CardSettlement).where(
            CardSettlement.id == settlement_id,
            CardSettlement.credit_card_id == credit_card_id,
        )
    )
    return result.scalar_one_or_none()


# Insert a new settlement.
async def create(session: AsyncSession, settlement: CardSettlement) -> CardSettlement:
    session.add(settlement)
    await session.flush()
    return settlement


# Delete a settlement.
async def delete(session: AsyncSession, settlement: CardSettlement) -> None:
    await session.delete(settlement)


# Clears the recorded cash leg on every settlement funded by this account, ahead of the account being
# deleted. The FK is ON DELETE SET NULL, so the row itself survives with its CARD leg intact and still
# clears its bucket correctly — but account_amount is denominated in the account that is going away, so
# leaving it behind would keep a figure nothing can interpret and break the invariant every reader
# relies on ("account_amount is set" ⇔ "this settlement crossed currencies").
async def clear_account_amounts(session: AsyncSession, account_id: int, user_id: int) -> None:
    await session.execute(
        update(CardSettlement).where(CardSettlement.account_id == account_id, CardSettlement.user_id == user_id).values(account_amount=None)
    )


# Nulls account_amount on every settlement of this user whose funding account is denominated in the
# settlement's OWN currency — i.e. where no conversion happened, so a second amount is meaningless.
# Scoped to the USER, not to the rows just restored: it therefore repairs any pre-existing row in that
# state too, which is the right blast radius because no legitimate row can match (a real cross-currency
# settlement has differing currencies; a real same-currency one already has account_amount NULL).
#
# Exists for the restore path, which bulk-inserts rows without passing through the service that owns this
# rule (_resolve_account_amount). A hand-edited export could otherwise pair a 700 ARS settlement with an
# ARS account and a 130,000 "cash leg", and all three cash sums would agree on debiting 130,000 — wrong
# by 129,300 with nothing able to see it, since the drift guard only proves the readers agree with each
# other. Cannot be a DB CHECK: the rule spans two tables.
async def clear_same_currency_account_amounts(session: AsyncSession, user_id: int) -> None:
    await session.execute(
        update(CardSettlement)
        .where(
            CardSettlement.user_id == user_id,
            CardSettlement.account_amount.isnot(None),
            CardSettlement.account_id == Account.id,
            Account.currency == CardSettlement.currency,
        )
        .values(account_amount=None)
    )


# Sum of settlements drawn from each account, grouped by account_id. Returns {account_id: total}.
# Sums the CASH leg: coalesce(account_amount, amount). A settlement may pay a bucket from an account in a
# DIFFERENT currency (paying a USD card with pesos), in which case `amount` is what cleared the bucket and
# account_amount is what actually left the account — summing `amount` here would add dollars into a peso
# balance. account_amount is NULL exactly when no conversion happened, so the coalesce falls back to the
# single amount and needs no per-currency split either way.
# as_of_date bounds the sum to rows dated on or before it (used by reconciliation's point-in-time balance).
# The join bounds it BELOW by the account's own opening_date: opening_balance is by definition the balance
# AT that date, so an earlier row is already inside it and summing it again double-counts.
async def sum_by_account_ids(
    session: AsyncSession,
    account_ids: list[int],
    user_id: int,
    *,
    as_of_date: date_type | None = None,
) -> dict[int, Decimal]:
    if not account_ids:
        return {}
    stmt = (
        select(CardSettlement.account_id, func.coalesce(func.sum(settlement_cash_leg()), 0))
        .join(Account, Account.id == CardSettlement.account_id)
        .where(CardSettlement.account_id.in_(account_ids), CardSettlement.user_id == user_id, CardSettlement.date >= Account.opening_date)
    )
    if as_of_date is not None:
        stmt = stmt.where(CardSettlement.date <= as_of_date)
    result = await session.execute(stmt.group_by(CardSettlement.account_id))
    return {account_id: Decimal(str(total)) for account_id, total in result.all()}


# Returns whether any settlement draws from this account (used to lock the account's currency once linked).
async def exists_by_account_id(session: AsyncSession, account_id: int, user_id: int) -> bool:
    result = await session.execute(
        select(CardSettlement.id).where(CardSettlement.account_id == account_id, CardSettlement.user_id == user_id).limit(1)
    )
    return result.first() is not None


# Monthly settlement totals drawn from each account, grouped by account_id, year, month. Sums the CASH
# leg for the same reason sum_by_account_ids does — this feeds the net-worth chart, so a cross-currency
# settlement counted at its card amount would move the chart by dollars in a peso account. Nothing
# cross-checks this path automatically, unlike the live balance, so it must be kept in step by hand.
# Returns a list of (account_id, year, month, total).
async def sum_by_account_ids_monthly(session: AsyncSession, account_ids: list[int], user_id: int) -> list[tuple[int, int, int, Decimal]]:
    if not account_ids:
        return []
    year_col = func.extract("year", CardSettlement.date).label("year")
    month_col = func.extract("month", CardSettlement.date).label("month")
    result = await session.execute(
        select(CardSettlement.account_id, year_col, month_col, func.coalesce(func.sum(settlement_cash_leg()), 0))
        .join(Account, Account.id == CardSettlement.account_id)
        .where(CardSettlement.account_id.in_(account_ids), CardSettlement.user_id == user_id, CardSettlement.date >= Account.opening_date)
        .group_by(CardSettlement.account_id, year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), Decimal(str(row[3]))) for row in result.all()]


# Sum of settlements grouped by credit card id and currency. Returns {card_id: {currency: total}}.
# Replaces the flat sum_by_card_ids — bucket balances need per-currency totals.
# Sums `amount`, the CARD leg, and must NOT use settlement_cash_leg(): a bucket is cleared by what the bank applied to
# it in the bucket's own currency, so a settlement paid in pesos still clears US$100 of a USD bucket.
async def sum_by_card_ids_grouped(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> dict[int, dict[str, float]]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            CardSettlement.credit_card_id,
            CardSettlement.currency,
            func.coalesce(func.sum(CardSettlement.amount), 0),
        )
        .where(CardSettlement.credit_card_id.in_(credit_card_ids))
        .group_by(CardSettlement.credit_card_id, CardSettlement.currency)
    )
    grouped: dict[int, dict[str, float]] = {}
    for card_id, currency, total in result.all():
        grouped.setdefault(card_id, {})[currency] = float(total)
    return grouped


# Monthly settlement totals for given credit cards, grouped by card_id, year, month, and currency.
# Sums the CARD leg (see sum_by_card_ids_grouped) — the card's own debt series, not what any account paid.
# Returns a list of (card_id, year, month, currency, total) tuples.
async def sum_by_card_ids_monthly(
    session: AsyncSession,
    credit_card_ids: list[int],
) -> list[tuple[int, int, int, str, float]]:
    if not credit_card_ids:
        return []
    year_col = func.extract("year", CardSettlement.date).label("year")
    month_col = func.extract("month", CardSettlement.date).label("month")
    result = await session.execute(
        select(
            CardSettlement.credit_card_id,
            year_col,
            month_col,
            CardSettlement.currency,
            func.coalesce(func.sum(CardSettlement.amount), 0),
        )
        .where(CardSettlement.credit_card_id.in_(credit_card_ids))
        .group_by(CardSettlement.credit_card_id, year_col, month_col, CardSettlement.currency)
        .order_by(year_col, month_col)
    )
    return [(row[0], int(row[1]), int(row[2]), row[3], float(row[4])) for row in result.all()]


# Which of the given accounts have any linked settlement row at all. Drives the currency lock, so unlike
# sum_by_account_ids it is NOT bounded by opening_date: a pre-opening row contributes nothing to the
# balance but its cash leg is still denominated in the account's currency, and re-denominating the account
# would silently reinterpret that stored figure. That holds for a cross-currency settlement too — there it
# is account_amount rather than amount that is denominated in the account's currency, which is exactly why
# the lock is still needed rather than being made redundant by recording both sides.
async def linked_account_ids(session: AsyncSession, account_ids: list[int], user_id: int) -> set[int]:
    if not account_ids:
        return set()
    result = await session.execute(
        select(CardSettlement.account_id)
        .where(CardSettlement.account_id.in_(account_ids), CardSettlement.user_id == user_id)
        .group_by(CardSettlement.account_id)
    )
    return {row[0] for row in result.all()}


# Namespace to call repository functions (e.g. card_settlement_repository.list_by_card).
class CardSettlementRepository:
    list_by_card = staticmethod(list_by_card)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    delete = staticmethod(delete)
    clear_account_amounts = staticmethod(clear_account_amounts)
    clear_same_currency_account_amounts = staticmethod(clear_same_currency_account_amounts)
    exists_by_account_id = staticmethod(exists_by_account_id)
    linked_account_ids = staticmethod(linked_account_ids)
    sum_by_account_ids = staticmethod(sum_by_account_ids)
    sum_by_account_ids_monthly = staticmethod(sum_by_account_ids_monthly)
    sum_by_card_ids_grouped = staticmethod(sum_by_card_ids_grouped)
    sum_by_card_ids_monthly = staticmethod(sum_by_card_ids_monthly)


# Singleton used by services to access card settlement persistence.
card_settlement_repository = CardSettlementRepository()
