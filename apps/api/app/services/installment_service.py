from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import AdvanceResult, CycleAdvanceDecision, InstallmentLockedFieldError, NotFoundError, ReverseResult
from app.models.installment import Installment
from app.models.user import User
from app.repositories import installment_repository
from app.services.auto_expense_service import closest_installment_cuota

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
# installment's `current_installment` cursor (Phase 3, follow-up 3b, revised by Item 9).
# Per Option C the advance fires ONLY when the matched cuota index equals the current
# cursor (`idx == current_installment`). When the matched cuota is ahead (pre-pay /
# mis-click) the link is saved but the cursor stays put — the scheduler's back-fill
# loop + the partial UNIQUE INDEX dedup catch up naturally, so intermediate cuotas
# still get expense rows instead of being silently skipped. `multi_jump` surfaces that
# case so Item 7's cursor-advance toast can compose the right copy. Returns
# `would_advance=False` with a sentinel `next_expected_date` (the plan's start_date)
# when the plan is fully paid; the soft-confirm dialog UX only renders for non-advance
# cases anyway, and the sentinel keeps callers from having to handle Optional.
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
    return CycleAdvanceDecision(
        would_advance=idx == installment.current_installment,
        distance_days=distance_days,
        next_expected_date=cuota_date,
        multi_jump=idx > installment.current_installment,
    )


# Advances `current_installment` past the cuota matched by a manual expense entry.
# Caller commits — this stages the change inside the expense-create transaction so the
# advance is atomic with the linked expense insert. Returns an AdvanceResult when the
# cursor moved (Phase 3, follow-up Item 7); None when no advance fired (multi-jump,
# back-dated, plan already fully paid, or the installment can't be found). Flips
# `is_active = False` when the advance carries the cursor past the final cuota — the
# result's `new_cursor` reads empty to signal the archive transition. Per Item 9's
# narrowed predicate `would_advance` only fires when the matched cuota equals the
# current cursor, so the post-advance cursor is always `current_installment + 1`.
async def advance_for_manual_entry(session: AsyncSession, installment_id: int, user: User, entry_date: date_type) -> AdvanceResult | None:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        return None
    decision = compute_installment_advance_for_manual_entry(installment, entry_date)
    if not decision.would_advance:
        return None
    previous = installment.current_installment
    installment.current_installment = previous + 1
    archived = installment.current_installment > installment.installments_count
    if archived:
        installment.is_active = False
    await installment_repository.save(session, installment)
    return AdvanceResult(
        plan_type="installment",
        plan_id=installment.id,
        plan_name=installment.name,
        previous_cursor=str(previous),
        new_cursor="" if archived else str(installment.current_installment),
        total_count=installment.installments_count,
    )


# Walks `current_installment` back by one cuota (Phase 3, follow-up Item 10). Caller
# commits. Used by expense_service when the most-recent linked expense for an installment
# is deleted or unlinked. Re-activates the plan ONLY when stepping back from the exact
# auto-archived state `current = count + 1` (the position the advance set when paying
# the final cuota) — a manual user-archive mid-plan stays archived. No-op when the
# installment can't be found, doesn't belong to the user, or the cursor is already at
# cuota 1 (no cuota 0 to step back to). `previous_cursor` reads empty (the archive
# sentinel) only when the reverse re-activates a fully-paid plan.
async def reverse_for_unlink(session: AsyncSession, installment_id: int, user: User) -> ReverseResult | None:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        return None
    if installment.current_installment <= 1:
        return None
    previous_cursor = installment.current_installment
    reactivated = previous_cursor == installment.installments_count + 1
    installment.current_installment -= 1
    if reactivated:
        installment.is_active = True
    await installment_repository.save(session, installment)
    return ReverseResult(
        plan_type="installment",
        plan_id=installment.id,
        plan_name=installment.name,
        previous_cursor="" if reactivated else str(previous_cursor),
        new_cursor=str(installment.current_installment),
        total_count=installment.installments_count,
    )
