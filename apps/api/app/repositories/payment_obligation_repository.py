from datetime import date as date_type

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.payment_obligation import PaymentObligation
from app.repositories.utils import apply_listing_filters

_SORT_COLUMNS = {
    "name": PaymentObligation.name,
    "amount": PaymentObligation.amount,
    "currency": PaymentObligation.currency,
    "next_due_date": PaymentObligation.next_due_date,
    "recurrence": PaymentObligation.recurrence,
    "category": PaymentObligation.category,
}


# List payment obligations for a user with optional search, sorting, and active filtering.
# `include_ids` (only honoured when `active_only=True`) widens the active filter so
# the listed archived obligations pointed to by include_ids are still returned — used
# by the expense form's edit dialog so a row linked to a since-archived obligation can
# still render the plan name in the linked-FK dropdown (Phase 3 audit-round-3 follow-up).
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
    include_ids: list[int] | None = None,
) -> list[PaymentObligation]:
    stmt = apply_listing_filters(
        select(PaymentObligation),
        PaymentObligation,
        user_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
        include_ids=include_ids,
        sort_columns=_SORT_COLUMNS,
        default_order=PaymentObligation.next_due_date,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Active obligations whose next_due_date is at or before the given upper bound.
# Used by the Payments Calendar to project recurrences forward inside a window —
# anchors after the window can't reach back, so we filter them out at the DB.
async def list_active_anchored_to_or_before(
    session: AsyncSession,
    user_id: int,
    upper_bound: date_type,
) -> list[PaymentObligation]:
    stmt = select(PaymentObligation).where(
        PaymentObligation.user_id == user_id,
        PaymentObligation.is_active.is_(True),
        PaymentObligation.next_due_date <= upper_bound,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# Get a single payment obligation by id and user_id.
async def get_by_id(session: AsyncSession, obligation_id: int, user_id: int) -> PaymentObligation | None:
    result = await session.execute(select(PaymentObligation).where(PaymentObligation.id == obligation_id, PaymentObligation.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new payment obligation.
async def create(session: AsyncSession, obligation: PaymentObligation) -> PaymentObligation:
    session.add(obligation)
    await session.flush()
    return obligation


# Stage a payment obligation for update (caller commits).
async def save(session: AsyncSession, obligation: PaymentObligation) -> None:
    session.add(obligation)


# Delete a payment obligation.
async def delete(session: AsyncSession, obligation: PaymentObligation) -> None:
    await session.delete(obligation)


# Count payment obligations linked to a specific credit card.
async def count_by_credit_card(session: AsyncSession, credit_card_id: int) -> int:
    result = await session.execute(select(func.count()).where(PaymentObligation.credit_card_id == credit_card_id))
    return int(result.scalar_one())


# Count payment obligations grouped by credit card id. Returns {card_id: count}.
async def count_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, int]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            PaymentObligation.credit_card_id,
            func.count(),
        )
        .where(PaymentObligation.credit_card_id.in_(credit_card_ids))
        .group_by(PaymentObligation.credit_card_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Namespace to call repository functions (e.g. payment_obligation_repository.list_by_user).
class PaymentObligationRepository:
    list_by_user = staticmethod(list_by_user)
    list_active_anchored_to_or_before = staticmethod(list_active_anchored_to_or_before)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    count_by_credit_card = staticmethod(count_by_credit_card)
    count_by_credit_card_ids = staticmethod(count_by_credit_card_ids)


# Singleton used by services to access payment obligation persistence.
payment_obligation_repository = PaymentObligationRepository()
