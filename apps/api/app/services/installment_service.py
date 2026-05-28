from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import InstallmentLockedFieldError, NotFoundError
from app.models.installment import Installment
from app.models.user import User
from app.repositories import installment_repository
from app.services.auto_expense_service import closest_installment_cuota
from app.services.subscription_service import CycleAdvanceDecision
from app.utils.dates import BILLING_CYCLE_MONTHLY, cycle_tolerance_days

# Contractual fields locked once any cuota has been charged (current_installment > 1).
# Always editable: name, current_installment (manual correction), is_active (archive).
LOCKED_FIELDS = (
    "total_amount",
    "installment_amount",
    "installments_count",
    "currency",
    "start_date",
    "payment_method",
    "credit_card_id",
)


# Returns the subset of locked field names whose update value differs from the existing record.
# A no-op write (same value) is allowed so partial PUTs that echo unchanged fields don't error.
def diff_locked_fields(existing: Installment, fields: dict[str, object]) -> list[str]:
    changed: list[str] = []
    for name in LOCKED_FIELDS:
        if name in fields and fields[name] != getattr(existing, name):
            changed.append(name)
    return changed


# List installments for a user with optional search, sorting, and archive filtering.
async def list_installments(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
) -> list[Installment]:
    return await installment_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
    )


# Get a single installment by id. Raises NotFoundError if not found.
async def get_installment(session: AsyncSession, installment_id: int, user: User) -> Installment:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        raise NotFoundError("Installment not found.")
    return installment


# Create a new installment plan.
async def create_installment(
    session: AsyncSession,
    user: User,
    *,
    name: str,
    total_amount: Decimal,
    installment_amount: Decimal,
    currency: str,
    installments_count: int,
    start_date: date_type,
    current_installment: int = 1,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
) -> Installment:
    installment = Installment(
        user_id=user.id,
        name=name,
        total_amount=total_amount,
        installment_amount=installment_amount,
        currency=currency,
        installments_count=installments_count,
        current_installment=current_installment,
        start_date=start_date,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
    )
    installment = await installment_repository.create(session, installment)
    await session.commit()
    return installment


# Update an existing installment plan. Only provided fields are changed.
# Once any cuota has been charged (current_installment > 1), contractual fields are locked
# and modifying them raises InstallmentLockedFieldError (mapped to 400).
async def update_installment(
    session: AsyncSession,
    installment_id: int,
    user: User,
    **fields: object,
) -> Installment:
    installment = await get_installment(session, installment_id, user)
    if installment.current_installment > 1:
        violated = diff_locked_fields(installment, fields)
        if violated:
            raise InstallmentLockedFieldError(violated)
    for key, value in fields.items():
        setattr(installment, key, value)
    await installment_repository.save(session, installment)
    await session.commit()
    await session.refresh(installment)
    return installment


# Delete an installment plan.
async def delete_installment(session: AsyncSession, installment_id: int, user: User) -> None:
    installment = await get_installment(session, installment_id, user)
    await installment_repository.delete(session, installment)
    await session.commit()


# Pure helper: decides whether a manual entry on `entry_date` should advance the
# installment's `current_installment` cursor (Phase 3, follow-up 3b). The advance fires
# only when the entry is within tolerance of the closest cuota AND that cuota's index
# sits at-or-after the current cursor (back-dated entries before the cursor never
# rewind — that's the reverse-advance feature's job). Returns `would_advance=False`
# with a sentinel `next_expected_date` (the plan's start_date) when the plan is fully
# paid; the soft-confirm dialog UX only renders for non-advance cases anyway, and the
# sentinel keeps callers from having to handle Optional.
def compute_installment_advance_for_manual_entry(installment: Installment, entry_date: date_type) -> CycleAdvanceDecision:
    closest = closest_installment_cuota(
        installment.start_date,
        installment.current_installment,
        installment.installments_count,
        entry_date,
    )
    if closest is None:
        return CycleAdvanceDecision(would_advance=False, distance_days=0, next_expected_date=installment.start_date)
    idx, cuota_date = closest
    distance_days = abs((entry_date - cuota_date).days)
    # Installments use the monthly cycle's tolerance unconditionally — the cuota grid
    # is by definition month-spaced regardless of any per-plan setting.
    tolerance = cycle_tolerance_days(BILLING_CYCLE_MONTHLY)
    in_tolerance = distance_days <= tolerance
    not_back_dated = idx >= installment.current_installment
    return CycleAdvanceDecision(
        would_advance=in_tolerance and not_back_dated,
        distance_days=distance_days,
        next_expected_date=cuota_date,
    )


# Advances `current_installment` past the cuota matched by a manual expense entry.
# Caller commits — this stages the change inside the expense-create transaction so the
# advance is atomic with the linked expense insert. Returns True when the cursor moved;
# False when out of tolerance, back-dated, or the plan was already fully paid. Flips
# `is_active = False` when the advance carries the cursor past the final cuota.
async def advance_for_manual_entry(session: AsyncSession, installment_id: int, user: User, entry_date: date_type) -> bool:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        return False
    decision = compute_installment_advance_for_manual_entry(installment, entry_date)
    if not decision.would_advance:
        return False
    # Re-derive the matched cuota index from the stored cuota date. closest_installment_cuota
    # guarantees `next_expected_date == start_date + (idx - 1) months`, so the index can be
    # recovered from the month delta without re-running the helper.
    months_offset = (decision.next_expected_date.year - installment.start_date.year) * 12 + (
        decision.next_expected_date.month - installment.start_date.month
    )
    matched_idx = months_offset + 1
    installment.current_installment = matched_idx + 1
    if installment.current_installment > installment.installments_count:
        installment.is_active = False
    await installment_repository.save(session, installment)
    return True
