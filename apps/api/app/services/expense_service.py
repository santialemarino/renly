from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.user import User
from app.repositories import expense_repository
from app.services import card_reconciliation_service


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
    )
    entry = await expense_repository.create(session, entry)
    if credit_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, credit_card_id, currency, date)
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
