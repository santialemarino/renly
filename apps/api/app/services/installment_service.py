from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AdvanceResult,
    CycleAdvanceDecision,
    InstallmentLockedFieldError,
    NotFoundError,
    PaymentMethod,
    PaymentPairingError,
    ReverseResult,
    closest_installment_cuota,
    installment_link_advanced_cursor,
)
from app.models.installment import Installment
from app.models.user import User
from app.repositories import credit_card_repository, installment_repository
from app.schemas.installment import InstallmentResponse
from app.services import account_service, exchange_rate_service
from app.utils.metrics import RateLookup, convert_optional

# Contractual fields locked once any installment has been charged (current_installment > 1).
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


# Maps an installment to its response, converting both amount fields at today's rate when a
# display currency is requested (plans are current-state rows, not historical events).
def _to_response(
    installment: Installment,
    currency: str | None,
    lookup: RateLookup | None,
    today: date_type,
) -> InstallmentResponse:
    resp = InstallmentResponse.model_validate(installment)
    resp.converted_total_amount = convert_optional(installment.total_amount, installment.currency, currency, lookup, today)
    resp.converted_installment_amount = convert_optional(installment.installment_amount, installment.currency, currency, lookup, today)
    return resp


# List installments for a user with optional search, sorting, archive filtering, and conversion.
# `include_ids` lets callers widen an active-only listing with specific archived plans
# so the expense edit dialog can still render the plan name of a since-archived link.
async def list_installments(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
    include_ids: list[int] | None = None,
    currency: str | None = None,
) -> list[InstallmentResponse]:
    installments = await installment_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
        include_ids=include_ids,
    )
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    # Rate anchor for the converted_* display fields: deliberately server-date, not the user's local
    # today. It only selects which daily FX map values a current-state amount; rates are never
    # future-dated, so server-date always bisects to the freshest stored rate, whereas a user-local
    # anchor (for a user behind UTC) could only pick a staler one. Not a period boundary.
    today = date_type.today()
    return [_to_response(i, currency, lookup, today) for i in installments]


# Get a single installment by id. Raises NotFoundError if not found.
async def get_installment(session: AsyncSession, installment_id: int, user: User) -> Installment:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        raise NotFoundError("Installment not found.")
    return installment


# Get a single installment as its response schema, converted when a display currency is requested.
async def get_installment_response(
    session: AsyncSession,
    installment_id: int,
    user: User,
    *,
    currency: str | None = None,
) -> InstallmentResponse:
    installment = await get_installment(session, installment_id, user)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    # Rate anchor for the converted_* display fields: deliberately server-date, not the user's local
    # today. It only selects which daily FX map values a current-state amount; rates are never
    # future-dated, so server-date always bisects to the freshest stored rate, whereas a user-local
    # anchor (for a user behind UTC) could only pick a staler one. Not a period boundary.
    today = date_type.today()
    return _to_response(installment, currency, lookup, today)


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
    default_account_id: int | None = None,
) -> Installment:
    # SEC-4: a plan must not reference another user's card (FK bypasses RLS).
    if credit_card_id is not None and await credit_card_repository.get_by_id(session, credit_card_id, user.id) is None:
        raise NotFoundError("Credit card not found")
    # The default funding account must be owned and match the plan's currency — the scheduler links it
    # onto every emitted cuota, and every account-linked row must be in that account's currency.
    await account_service.validate_account_link(session, user, default_account_id, currency)
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
        default_account_id=default_account_id,
    )
    installment = await installment_repository.create(session, installment)
    await session.commit()
    return installment


# Update an existing installment plan. Only provided fields are changed.
# Once any installment has been charged (current_installment > 1), contractual fields are
# locked and modifying them raises InstallmentLockedFieldError (mapped to 400).
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
    # Effective payment pairing after the merge + SEC-4 ownership on a newly-set card.
    new_card_id = fields.get("credit_card_id", installment.credit_card_id)
    new_method = fields.get("payment_method", installment.payment_method)
    if new_card_id is not None and new_method != PaymentMethod.credit_card:
        raise PaymentPairingError()
    if new_card_id is not None and new_card_id != installment.credit_card_id:
        if await credit_card_repository.get_by_id(session, new_card_id, user.id) is None:
            raise NotFoundError("Credit card not found")
    # Effective default funding account after the merge: a card-paid plan never draws an account (its
    # cash leg lands at the card settlement), and the account must still match the effective currency.
    # Deliberately NOT one of the LOCKED_FIELDS — it is a forward-looking convenience rather than a
    # contractual term, so it stays editable once charging has started.
    await account_service.validate_effective_default_link(
        session,
        user,
        fields=fields,
        stored_account_id=installment.default_account_id,
        stored_currency=installment.currency,
        effective_method=new_method,
    )
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
# Per Option C the advance fires ONLY when the matched installment index equals the
# current cursor (`idx == current_installment`). When the matched installment is ahead
# (pre-pay / mis-click) the link is saved but the cursor stays put — the scheduler's
# back-fill loop + the partial UNIQUE INDEX dedup catch up naturally, so intermediate
# installments still get expense rows instead of being silently skipped. `multi_jump` surfaces that
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


# Advances `current_installment` past the installment matched by a manual expense entry.
# Caller commits — this stages the change inside the expense-create transaction so the
# advance is atomic with the linked expense insert. Returns an AdvanceResult when the
# cursor moved (Phase 3, follow-up Item 7); None when no advance fired (multi-jump,
# back-dated, plan already fully paid, or the installment can't be found). Flips
# `is_active = False` when the advance carries the cursor past the final installment —
# the result's `new_cursor` reads empty to signal the archive transition. Per Item 9's
# narrowed predicate `would_advance` only fires when the matched installment equals the
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


# Walks `current_installment` back by one step (Phase 3, follow-up Item 10). Caller
# commits. Used by expense_service when the most-recent linked expense for an installment
# is deleted or unlinked. Re-activates the plan ONLY when stepping back from the exact
# auto-archived state `current = count + 1` (the position the advance set when paying
# the final installment) — a manual user-archive mid-plan stays archived. No-op when the
# installment can't be found, doesn't belong to the user, or the cursor is already at
# installment 1 (no installment 0 to step back to). `previous_cursor` reads empty (the
# archive sentinel) only when the reverse re-activates a fully-paid plan.
# The reverse fires only when the deleted expense binds to the cuota immediately before the
# cursor (recomputed via the create path's matcher) — deleting a historical or pre-pay link
# is a no-op.
async def reverse_for_unlink(session: AsyncSession, installment_id: int, user: User, entry_date: date_type) -> ReverseResult | None:
    installment = await installment_repository.get_by_id(session, installment_id, user.id)
    if installment is None:
        return None
    if installment.current_installment <= 1:
        return None
    if not installment_link_advanced_cursor(
        installment.start_date,
        installment.current_installment,
        installment.installments_count,
        entry_date,
    ):
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
