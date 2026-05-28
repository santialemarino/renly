from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.user import User
from app.repositories import expense_repository, installment_repository, subscription_repository
from app.services import card_reconciliation_service, payment_obligation_service

# Match window for the manual-dupe expense warning (Phase 3, Step D). Mirrors the
# user-facing constant DUPE_MATCH_WINDOW_DAYS in apps/web/lib/constants/expenses.ts.
DUPE_MATCH_WINDOW_DAYS = 15


# Result of an auto-charge match lookup. Returned by find_auto_charge_match and
# shaped by the router into AutoChargeMatchResponse.
@dataclass(frozen=True)
class AutoChargeMatchResult:
    expense_id: int
    date: date_type
    source: str
    source_plan_id: int
    source_plan_name: str


# List expenses for a user with optional filters and pagination.
async def list_expenses(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    category: ExpenseCategory | None = None,
    payment_method: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    page: int = 1,
    page_size: int = 25,
) -> tuple[list[ExpenseEntry], int]:
    return await expense_repository.list_by_user_filtered(
        session,
        user.id,
        search=search,
        category=category,
        payment_method=payment_method,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )


# Get a single expense by id. Raises NotFoundError if not found.
async def get_expense(session: AsyncSession, expense_id: int, user: User) -> ExpenseEntry:
    entry = await expense_repository.get_by_id(session, expense_id, user.id)
    if entry is None:
        raise NotFoundError("Expense not found.")
    return entry


# Create a new expense entry. Marks any reconciliation covering the entry's date stale (Phase 3, Step 5).
# When payment_obligation_id is set, advances or archives the linked obligation atomically (Phase 3, Step E).
# subscription_id / installment_id are stored on the row but do not advance the scheduler's cursor in 3a —
# that's deferred to 3b (smart dedup + auto-advance).
async def create_expense(
    session: AsyncSession,
    user: User,
    *,
    date: date_type,
    amount: Decimal,
    currency: str,
    category: ExpenseCategory | None = None,
    notes: str | None = None,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
    source: str = "manual",
    payment_obligation_id: int | None = None,
    subscription_id: int | None = None,
    installment_id: int | None = None,
) -> ExpenseEntry:
    entry = ExpenseEntry(
        user_id=user.id,
        date=date,
        amount=amount,
        currency=currency,
        category=category,
        notes=notes,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        source=source,
        payment_obligation_id=payment_obligation_id,
        subscription_id=subscription_id,
        installment_id=installment_id,
    )
    entry = await expense_repository.create(session, entry)
    if credit_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, credit_card_id, currency, date)
    if payment_obligation_id is not None:
        await payment_obligation_service.advance_or_archive(session, payment_obligation_id, user)
    await session.commit()
    return entry


# Update an existing expense entry. Only provided fields are changed.
# Marks stale on both the prior and the new (card, currency, date) when either has credit_card_id.
async def update_expense(
    session: AsyncSession,
    expense_id: int,
    user: User,
    **fields: object,
) -> ExpenseEntry:
    entry = await get_expense(session, expense_id, user)
    old_card_id = entry.credit_card_id
    old_currency = entry.currency
    old_date = entry.date
    for key, value in fields.items():
        setattr(entry, key, value)
    await expense_repository.save(session, entry)

    if old_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, old_card_id, old_currency, old_date)
    moved = entry.credit_card_id != old_card_id or entry.currency != old_currency or entry.date != old_date
    if entry.credit_card_id is not None and moved:
        await card_reconciliation_service.mark_stale_for_date(session, entry.credit_card_id, entry.currency, entry.date)

    await session.commit()
    await session.refresh(entry)
    return entry


# Delete an expense entry. Marks any reconciliation covering the entry's date stale.
async def delete_expense(session: AsyncSession, expense_id: int, user: User) -> None:
    entry = await get_expense(session, expense_id, user)
    old_card_id = entry.credit_card_id
    old_currency = entry.currency
    old_date = entry.date
    await expense_repository.delete(session, entry)
    if old_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, old_card_id, old_currency, old_date)
    await session.commit()


# Looks up the most recent scheduler-generated expense (source IN subscription/installment)
# that matches the candidate manual entry on card/currency/amount within ±DUPE_MATCH_WINDOW_DAYS.
# `exclude_expense_id` is passed from the edit flow so the row being edited doesn't match
# itself when it happens to be auto-tagged. Returns None when nothing matches.
async def find_auto_charge_match(
    session: AsyncSession,
    user: User,
    *,
    credit_card_id: int,
    currency: str,
    amount: Decimal,
    target_date: date_type,
    exclude_expense_id: int | None = None,
) -> AutoChargeMatchResult | None:
    match = await expense_repository.find_auto_charge_match(
        session,
        user.id,
        credit_card_id=credit_card_id,
        currency=currency,
        amount=amount,
        target_date=target_date,
        window_days=DUPE_MATCH_WINDOW_DAYS,
        exclude_expense_id=exclude_expense_id,
    )
    if match is None:
        return None
    if match.source == "subscription" and match.subscription_id is not None:
        plan = await subscription_repository.get_by_id(session, match.subscription_id, user.id)
    elif match.source == "installment" and match.installment_id is not None:
        plan = await installment_repository.get_by_id(session, match.installment_id, user.id)
    else:
        return None
    if plan is None:
        return None
    return AutoChargeMatchResult(
        expense_id=match.id,
        date=match.date,
        source=match.source,
        source_plan_id=plan.id,
        source_plan_name=plan.name,
    )
