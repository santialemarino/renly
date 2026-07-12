from datetime import date as date_type

from sqlalchemy import Date, cast, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models.installment import Installment
from app.repositories.utils import apply_listing_filters

# Derived expression matching the `InstallmentResponse.next_cuota_date` computed field.
# Lets the table sort by next-installment order without an O(n) post-query Python re-sort —
# `make_interval` is a PostgreSQL built-in that handles month-end clamping the same
# way `add_months` does on the Python side (e.g. Jan 31 + 1 month → Feb 28), so the
# SQL order matches the response values exactly. Cast back to Date because
# `date + interval` returns timestamp in PG.
_next_cuota_date_expr = cast(
    Installment.start_date + func.make_interval(0, Installment.current_installment - 1),
    Date,
)

_SORT_COLUMNS = {
    "name": Installment.name,
    "total_amount": Installment.total_amount,
    "installment_amount": Installment.installment_amount,
    "currency": Installment.currency,
    "installments_count": Installment.installments_count,
    "current_installment": Installment.current_installment,
    "start_date": Installment.start_date,
    "next_cuota_date": _next_cuota_date_expr,
}


# List installments for a user with optional search, sorting, and active filtering.
# `include_ids` (only honoured when `active_only=True`) widens the active filter so
# the listed archived plans pointed to by include_ids are still returned — used by
# the expense form's edit dialog so a row linked to a since-archived plan can still
# render the plan name in the linked-FK dropdown (Phase 3 audit-round-3 follow-up).
async def list_by_user(
    session: AsyncSession,
    user_id: int,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
    include_ids: list[int] | None = None,
) -> list[Installment]:
    stmt = apply_listing_filters(
        select(Installment),
        Installment,
        user_id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
        include_ids=include_ids,
        sort_columns=_SORT_COLUMNS,
        # Default order: most-recent first by the derived next-installment date — keeps the
        # default view aligned with what the table now leads with.
        default_order=_next_cuota_date_expr.desc(),
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# List every active installment plan (cluster-wide) whose next cuota date — the derived
# start_date + (current_installment - 1) months expression, month-end clamped exactly like the
# Python add_months — is at or before `cutoff` (inclusive). The unfinished-plan bound mirrors the
# service's own current_installment <= installments_count filter. Powers the hourly auto-expense scan.
async def list_active_due(session: AsyncSession, cutoff: date_type) -> list[Installment]:
    result = await session.execute(
        select(Installment).where(
            Installment.is_active.is_(True),
            Installment.current_installment <= Installment.installments_count,
            _next_cuota_date_expr <= cutoff,
        )
    )
    return list(result.scalars().all())


# Get a single installment by id and user_id.
async def get_by_id(session: AsyncSession, installment_id: int, user_id: int) -> Installment | None:
    result = await session.execute(select(Installment).where(Installment.id == installment_id, Installment.user_id == user_id))
    return result.scalar_one_or_none()


# Insert a new installment plan.
async def create(session: AsyncSession, installment: Installment) -> Installment:
    session.add(installment)
    await session.flush()
    return installment


# Stage an installment for update (caller commits).
async def save(session: AsyncSession, installment: Installment) -> None:
    session.add(installment)


# Delete an installment.
async def delete(session: AsyncSession, installment: Installment) -> None:
    await session.delete(installment)


# Count installment plans linked to a specific credit card.
async def count_by_credit_card(session: AsyncSession, credit_card_id: int) -> int:
    result = await session.execute(select(func.count()).where(Installment.credit_card_id == credit_card_id))
    return int(result.scalar_one())


# Count installment plans grouped by credit card id. Returns {card_id: count}.
async def count_by_credit_card_ids(session: AsyncSession, credit_card_ids: list[int]) -> dict[int, int]:
    if not credit_card_ids:
        return {}
    result = await session.execute(
        select(
            Installment.credit_card_id,
            func.count(),
        )
        .where(Installment.credit_card_id.in_(credit_card_ids))
        .group_by(Installment.credit_card_id)
    )
    return {row[0]: int(row[1]) for row in result.all()}


# Namespace to call repository functions (e.g. installment_repository.list_by_user).
class InstallmentRepository:
    list_by_user = staticmethod(list_by_user)
    list_active_due = staticmethod(list_active_due)
    get_by_id = staticmethod(get_by_id)
    create = staticmethod(create)
    save = staticmethod(save)
    delete = staticmethod(delete)
    count_by_credit_card = staticmethod(count_by_credit_card)
    count_by_credit_card_ids = staticmethod(count_by_credit_card_ids)


# Singleton used by services to access installment persistence.
installment_repository = InstallmentRepository()
