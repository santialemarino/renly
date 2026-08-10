from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import (
    AccountCardExclusivityError,
    AdvanceResult,
    NotFoundError,
    PaymentMethod,
    PaymentPairingError,
    ReverseResult,
)
from app.models.expense_entry import ExpenseCategory
from app.models.payment_obligation import PaymentObligation
from app.models.user import User
from app.repositories import credit_card_repository, expense_repository, payment_obligation_repository
from app.schemas.payment_obligation import PaymentObligationResponse
from app.services import account_service, exchange_rate_service
from app.utils.dates import OBLIGATION_MONTH_STEP, add_months_anchored
from app.utils.metrics import RateLookup, convert_optional


# Maps an obligation to its response, converting the amount at today's rate when a display
# currency is requested (obligations are current-state rows, not historical events).
def _to_response(
    obligation: PaymentObligation,
    currency: str | None,
    lookup: RateLookup | None,
    today: date_type,
) -> PaymentObligationResponse:
    resp = PaymentObligationResponse.model_validate(obligation)
    resp.converted_amount = convert_optional(obligation.amount, obligation.currency, currency, lookup, today)
    return resp


# List payment obligations for a user with optional search, sorting, archive filtering, and
# conversion. `include_ids` lets callers widen an active-only listing with specific archived
# obligations so the expense edit dialog can still render the name of a since-archived link.
async def list_obligations(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str = "asc",
    active_only: bool = True,
    include_ids: list[int] | None = None,
    currency: str | None = None,
) -> list[PaymentObligationResponse]:
    obligations = await payment_obligation_repository.list_by_user(
        session,
        user.id,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        active_only=active_only,
        include_ids=include_ids,
    )
    # Batch-load latest-paid date per obligation in one query so archived one-off rows
    # can display "Paid on YYYY-MM-DD" without an N+1 lookup (Phase 3, Step E, 6.i).
    last_paid_dates = await expense_repository.max_linked_obligation_dates(session, user.id, [o.id for o in obligations])
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    # Rate anchor for the converted_* display fields: deliberately server-date, not the user's local
    # today. It only selects which daily FX map values a current-state amount; rates are never
    # future-dated, so server-date always bisects to the freshest stored rate, whereas a user-local
    # anchor (for a user behind UTC) could only pick a staler one. Not a period boundary.
    today = date_type.today()
    responses: list[PaymentObligationResponse] = []
    for o in obligations:
        resp = _to_response(o, currency, lookup, today)
        resp.last_payment_date = last_paid_dates.get(o.id)
        responses.append(resp)
    return responses


# Get a single payment obligation by id. Raises NotFoundError if not found.
async def get_obligation(session: AsyncSession, obligation_id: int, user: User) -> PaymentObligation:
    obligation = await payment_obligation_repository.get_by_id(session, obligation_id, user.id)
    if obligation is None:
        raise NotFoundError("Payment obligation not found.")
    return obligation


# Get a single obligation as its response schema, converted when a display currency is requested.
async def get_obligation_response(
    session: AsyncSession,
    obligation_id: int,
    user: User,
    *,
    currency: str | None = None,
) -> PaymentObligationResponse:
    obligation = await get_obligation(session, obligation_id, user)
    last_paid_dates = await expense_repository.max_linked_obligation_dates(session, user.id, [obligation.id])
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    # Rate anchor for the converted_* display fields: deliberately server-date, not the user's local
    # today. It only selects which daily FX map values a current-state amount; rates are never
    # future-dated, so server-date always bisects to the freshest stored rate, whereas a user-local
    # anchor (for a user behind UTC) could only pick a staler one. Not a period boundary.
    today = date_type.today()
    resp = _to_response(obligation, currency, lookup, today)
    resp.last_payment_date = last_paid_dates.get(obligation.id)
    return resp


# Create a new payment obligation. Auto-derives anchor_day from next_due_date.day so
# day-31 recurrences walk the calendar without drifting across short-month clamps.
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
    default_account_id: int | None = None,
    notes: str | None = None,
) -> PaymentObligation:
    # SEC-4: a plan must not reference another user's card (FK bypasses RLS).
    if credit_card_id is not None and await credit_card_repository.get_by_id(session, credit_card_id, user.id) is None:
        raise NotFoundError("Credit card not found")
    # The default funding account must be owned and match the obligation's currency — Mark Paid copies
    # it onto the expense it creates, and every account-linked row must be in that account's currency.
    await account_service.validate_account_link(session, user, default_account_id, currency)
    obligation = PaymentObligation(
        user_id=user.id,
        name=name,
        amount=amount,
        currency=currency,
        next_due_date=next_due_date,
        anchor_day=next_due_date.day,
        recurrence=recurrence,
        category=category,
        expense_category=expense_category,
        payment_method=payment_method,
        credit_card_id=credit_card_id,
        default_account_id=default_account_id,
        notes=notes,
    )
    obligation = await payment_obligation_repository.create(session, obligation)
    await session.commit()
    return obligation


# Update an existing payment obligation. Only provided fields are changed.
# When next_due_date changes, anchor_day is re-derived from the new value — manual
# edits represent the user redeclaring the cadence's anchor (e.g. landlord switched
# billing day), so the new day becomes the truth-of-record for future advances.
async def update_obligation(
    session: AsyncSession,
    obligation_id: int,
    user: User,
    **fields: object,
) -> PaymentObligation:
    obligation = await get_obligation(session, obligation_id, user)
    # Effective payment pairing after the merge + SEC-4 ownership on a newly-set card.
    new_card_id = fields.get("credit_card_id", obligation.credit_card_id)
    new_method = fields.get("payment_method", obligation.payment_method)
    if new_card_id is not None and new_method != PaymentMethod.credit_card:
        raise PaymentPairingError()
    if new_card_id is not None and new_card_id != obligation.credit_card_id:
        if await credit_card_repository.get_by_id(session, new_card_id, user.id) is None:
            raise NotFoundError("Credit card not found")
    # Effective default funding account after the merge: a card-paid obligation never draws an account
    # (its cash leg lands at the card settlement), and the account must still match the effective currency.
    new_default_account_id = fields.get("default_account_id", obligation.default_account_id)
    new_currency = fields.get("currency") or obligation.currency
    if new_default_account_id is not None and new_method == PaymentMethod.credit_card:
        raise AccountCardExclusivityError()
    # Only re-validated when the pair actually MOVES: an unchanged pair was already validated when it
    # was attached, and re-checking it would let a stale stored default (its account's currency changed
    # while nothing else referenced it) block an unrelated edit such as a rename or an archive.
    if new_default_account_id != obligation.default_account_id or new_currency != obligation.currency:
        await account_service.validate_account_link(session, user, new_default_account_id, new_currency)
    for key, value in fields.items():
        setattr(obligation, key, value)
    if "next_due_date" in fields and fields["next_due_date"] is not None:
        obligation.anchor_day = obligation.next_due_date.day
    await payment_obligation_repository.save(session, obligation)
    await session.commit()
    await session.refresh(obligation)
    return obligation


# Delete a payment obligation.
async def delete_obligation(session: AsyncSession, obligation_id: int, user: User) -> None:
    obligation = await get_obligation(session, obligation_id, user)
    await payment_obligation_repository.delete(session, obligation)
    await session.commit()


# Pure helper: given an obligation's current next_due_date + recurrence + anchor_day,
# returns the post-advance (next_due_date, is_active) pair. Recurring obligations move
# next_due_date forward by one recurrence cycle, anchored on anchor_day (NOT next_due_date.day)
# so a 31st-of-month obligation walks Jan 31 -> Feb 28 -> Mar 31 -> Apr 30 -> May 31 without
# drift when prior advances were clamped. One-off obligations flip is_active to False.
# Returns (next_due_date, True) unchanged when the recurrence value is unrecognised —
# defensive default so a corrupt record doesn't disable the obligation by accident.
def compute_obligation_advance(next_due_date: date_type, recurrence: str | None, anchor_day: int) -> tuple[date_type, bool]:
    if recurrence is None:
        return next_due_date, False
    months_step = OBLIGATION_MONTH_STEP.get(recurrence)
    if months_step is None:
        return next_due_date, True
    return add_months_anchored(next_due_date, months_step, anchor_day), True


# Advances next_due_date one recurrence cycle (recurring) or archives the obligation (one-off).
# Caller commits — this stages the change inside the expense-create transaction so the advance
# is atomic with the linked expense insert (Phase 3, Step E). Returns an AdvanceResult so the
# expense create response can carry enough context for the frontend toast (Phase 3, follow-up
# Item 7) — `new_cursor` is empty when a one-off obligation flips to is_active=False. None
# when the obligation can't be found or doesn't belong to the user.
async def advance_or_archive(session: AsyncSession, obligation_id: int, user: User) -> AdvanceResult | None:
    obligation = await payment_obligation_repository.get_by_id(session, obligation_id, user.id)
    if obligation is None:
        return None
    previous = obligation.next_due_date
    obligation.next_due_date, obligation.is_active = compute_obligation_advance(
        obligation.next_due_date, obligation.recurrence, obligation.anchor_day
    )
    await payment_obligation_repository.save(session, obligation)
    archived = not obligation.is_active
    return AdvanceResult(
        plan_type="obligation",
        plan_id=obligation.id,
        plan_name=obligation.name,
        previous_cursor=previous.isoformat(),
        new_cursor="" if archived else obligation.next_due_date.isoformat(),
    )


# Walks next_due_date back one recurrence cycle (recurring) or re-activates the obligation
# (one-off; date is already correct since archive didn't move it). Caller commits. Used by
# expense_service when the most-recent linked expense for an obligation is deleted or
# unlinked (Phase 3, follow-up Item 10). Returns a ReverseResult with the cursor delta
# for Item 7's toast — `previous_cursor` reads empty (the archive sentinel) for one-off
# re-activations so the frontend can branch on the archive state. Recurring obligations
# never re-activate here: `compute_obligation_advance` only sets `is_active=False` for
# one-off (recurrence=None); a recurring obligation with `is_active=False` reflects a
# manual user archive, which the reverse must NOT override. No-op when the obligation
# can't be found.
async def reverse_for_unlink(session: AsyncSession, obligation_id: int, user: User) -> ReverseResult | None:
    obligation = await payment_obligation_repository.get_by_id(session, obligation_id, user.id)
    if obligation is None:
        return None
    previous_date = obligation.next_due_date
    reactivated = False
    if obligation.recurrence is None:
        # One-off obligations don't walk the date back; the archive flip is what undoes the advance.
        obligation.is_active = True
        reactivated = True
    elif obligation.recurrence in OBLIGATION_MONTH_STEP:
        # Recurring obligations step back by their full recurrence cycle, mirroring the
        # forward advance in compute_obligation_advance. is_active is left untouched.
        obligation.next_due_date = add_months_anchored(
            obligation.next_due_date,
            -OBLIGATION_MONTH_STEP[obligation.recurrence],
            obligation.anchor_day,
        )
    else:
        # Unknown recurrence: defensive default mirrors compute_obligation_advance's no-op.
        return None
    await payment_obligation_repository.save(session, obligation)
    return ReverseResult(
        plan_type="obligation",
        plan_id=obligation.id,
        plan_name=obligation.name,
        previous_cursor="" if reactivated else previous_date.isoformat(),
        new_cursor=obligation.next_due_date.isoformat(),
    )
