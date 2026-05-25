from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError
from app.models.expense_entry import ExpenseCategory
from app.models.payment_obligation import PaymentObligation
from app.models.user import User
from app.repositories import payment_obligation_repository
from app.utils.dates import add_months_anchored

# Recurrence pattern -> calendar-month step. Public so the Payments Calendar
# (forward / backward walkers) and the expense -> obligation auto-advance share a single map.
OBLIGATION_MONTH_STEP: dict[str, int] = {
    "monthly": 1,
    "bimonthly": 2,
    "quarterly": 3,
    "annual": 12,
}


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
    next_due_date: date_type,
    recurrence: str | None = None,
    category: str | None = None,
    expense_category: ExpenseCategory | None = None,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
    notes: str | None = None,
) -> PaymentObligation:
    obligation = PaymentObligation(
        user_id=user.id,
        name=name,
        amount=amount,
        currency=currency,
        next_due_date=next_due_date,
        recurrence=recurrence,
        category=category,
        expense_category=expense_category,
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


# Pure helper: given an obligation's current next_due_date + recurrence, returns the post-advance
# (next_due_date, is_active) pair. Recurring obligations move next_due_date forward by one
# recurrence cycle (anchor-day preserved across short-month clamps). One-off obligations flip
# is_active to False. Returns (next_due_date, True) unchanged when the recurrence value is
# unrecognised — defensive default so a corrupt record doesn't disable the obligation by
# accident.
def compute_obligation_advance(next_due_date: date_type, recurrence: str | None) -> tuple[date_type, bool]:
    if recurrence is None:
        return next_due_date, False
    months_step = OBLIGATION_MONTH_STEP.get(recurrence)
    if months_step is None:
        return next_due_date, True
    return add_months_anchored(next_due_date, months_step, next_due_date.day), True


# Advances next_due_date one recurrence cycle (recurring) or archives the obligation (one-off).
# Caller commits — this stages the change inside the expense-create transaction so the advance
# is atomic with the linked expense insert (Phase 3, Step E). No-op when the obligation
# can't be found or doesn't belong to the user.
async def advance_or_archive(session: AsyncSession, obligation_id: int, user: User) -> None:
    obligation = await payment_obligation_repository.get_by_id(session, obligation_id, user.id)
    if obligation is None:
        return
    obligation.next_due_date, obligation.is_active = compute_obligation_advance(obligation.next_due_date, obligation.recurrence)
    await payment_obligation_repository.save(session, obligation)
