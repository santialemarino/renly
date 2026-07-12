from dataclasses import dataclass, replace
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import AdvanceResult, CycleAdvanceDecision, NotFoundError, PaymentMethod, PaymentPairingError, ReverseResult
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.user import User
from app.repositories import (
    credit_card_repository,
    expense_repository,
    installment_repository,
    payment_obligation_repository,
    subscription_repository,
)
from app.schemas.expense import ExpenseListResponse, ExpenseResponse
from app.services import (
    card_reconciliation_service,
    exchange_rate_service,
    installment_service,
    payment_obligation_service,
    settings_service,
    subscription_service,
)
from app.utils.dates import OBLIGATION_MONTH_STEP
from app.utils.metrics import RateLookup, convert_optional

# Match window for the manual-dupe expense warning (Phase 3, Step D). Mirrors the
# user-facing constant DUPE_MATCH_WINDOW_DAYS in apps/web/lib/constants/expenses.ts.
DUPE_MATCH_WINDOW_DAYS = 15

# Cap for the multi-cycle Mark Paid path (Phase 3, follow-up Item 2). Mirrors the web
# constant MAX_CYCLES_TO_ADVANCE in apps/web/app/(protected)/expenses/expenses-form-schema.ts.
# Enforced at the schema layer via `Field(le=...)` on ExpenseCreate.cycles_to_advance; the
# service references this constant for defensive guards.
MAX_CYCLES_PER_MARK_PAID = 12


# Result of an auto-charge match lookup. Returned by find_auto_charge_match and
# shaped by the router into AutoChargeMatchResponse.
@dataclass(frozen=True)
class AutoChargeMatchResult:
    expense_id: int
    date: date_type
    source: str
    source_plan_id: int
    source_plan_name: str


# Maps an entry to its response, converting at the entry's historical date (Phase 3, Step C).
# Expenses are records of past events — the display value reflects the rate in effect when the
# expense actually happened, so re-opening the page on a different day shows the same number.
def _to_response(entry: ExpenseEntry, currency: str | None, lookup: RateLookup | None) -> ExpenseResponse:
    resp = ExpenseResponse.model_validate(entry)
    resp.converted_amount = convert_optional(entry.amount, entry.currency, currency, lookup, entry.date)
    return resp


# List expenses for a user with optional filters, pagination, and display-currency conversion.
async def list_expenses(
    session: AsyncSession,
    user: User,
    *,
    search: str | None = None,
    category: ExpenseCategory | None = None,
    payment_method: str | None = None,
    date_from: date_type | None = None,
    date_to: date_type | None = None,
    currency: str | None = None,
    page: int = 1,
    page_size: int = 25,
) -> ExpenseListResponse:
    entries, total = await expense_repository.list_by_user_filtered(
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
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    items: list[ExpenseResponse] = []
    skipped: set[str] = set()
    for e in entries:
        resp = _to_response(e, currency, lookup)
        # A requested conversion that yielded null means the rate was missing — flag the row's currency.
        if currency and e.currency != currency and resp.converted_amount is None:
            skipped.add(e.currency)
        items.append(resp)
    return ExpenseListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        display_currency=currency,
        skipped_currencies=sorted(skipped),
    )


# Get a single expense by id. Raises NotFoundError if not found.
async def get_expense(session: AsyncSession, expense_id: int, user: User) -> ExpenseEntry:
    entry = await expense_repository.get_by_id(session, expense_id, user.id)
    if entry is None:
        raise NotFoundError("Expense not found.")
    return entry


# Get a single expense as its response schema, converted when a display currency is requested.
async def get_expense_response(
    session: AsyncSession,
    expense_id: int,
    user: User,
    *,
    currency: str | None = None,
) -> ExpenseResponse:
    entry = await get_expense(session, expense_id, user)
    lookup = await exchange_rate_service.get_user_rate_lookup(session, user.id) if currency else None
    return _to_response(entry, currency, lookup)


# Inserts the expense row. Extracted (Phase 3, follow-up Item 2) so create_expense and
# create_expenses_for_obligation_cycles can share the per-row insert pattern without
# duplication. Does NOT commit, does NOT advance any plan cursor, and does NOT stage the
# reconciliation-stale mark — caller owns the transaction boundary and is responsible for
# the stale-mark (only needed once per (card, currency, date) regardless of how many rows
# the caller inserts). Mirrors the field shape of ExpenseEntry / ExpenseCreate.
async def _insert_expense_row(
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
    return await expense_repository.create(session, entry)


# Validates that every provided FK belongs to the user, raising NotFoundError (router -> 404) for
# any that don't. Stops an expense from being attached to — or stale-marking — another user's
# credit card / payment obligation / subscription / installment (SEC-4).
async def _validate_owned_fks(
    session: AsyncSession,
    user: User,
    *,
    credit_card_id: int | None = None,
    payment_obligation_id: int | None = None,
    subscription_id: int | None = None,
    installment_id: int | None = None,
) -> None:
    if credit_card_id is not None and await credit_card_repository.get_by_id(session, credit_card_id, user.id) is None:
        raise NotFoundError("Credit card not found")
    if payment_obligation_id is not None and await payment_obligation_repository.get_by_id(session, payment_obligation_id, user.id) is None:
        raise NotFoundError("Payment obligation not found")
    if subscription_id is not None and await subscription_repository.get_by_id(session, subscription_id, user.id) is None:
        raise NotFoundError("Subscription not found")
    if installment_id is not None and await installment_repository.get_by_id(session, installment_id, user.id) is None:
        raise NotFoundError("Installment not found")


# Create a new expense entry. Marks any reconciliation covering the entry's date stale (Phase 3, Step 5).
# When payment_obligation_id is set, advances or archives the linked obligation atomically (Phase 3, Step E).
# When subscription_id or installment_id is set, advances the plan's cursor past the matched cycle
# when the matched cycle equals the current cursor (Phase 3, follow-up 3b, revised by Item 9);
# multi-jump / back-dated entries are persisted with the FK but leave the cursor untouched.
# Returns (entry, advance_result) — advance_result is None unless one of the three plan branches
# actually moved the cursor (Phase 3, follow-up Item 7); the router includes it in the response
# so the frontend toast can announce the schedule change. Mutual exclusivity at the schema layer
# means at most one branch fires per save.
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
) -> tuple[ExpenseEntry, AdvanceResult | None]:
    await _validate_owned_fks(
        session,
        user,
        credit_card_id=credit_card_id,
        payment_obligation_id=payment_obligation_id,
        subscription_id=subscription_id,
        installment_id=installment_id,
    )
    entry = await _insert_expense_row(
        session,
        user,
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
    if credit_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, credit_card_id, currency, date)
    advance_result: AdvanceResult | None = None
    if payment_obligation_id is not None:
        advance_result = await payment_obligation_service.advance_or_archive(session, payment_obligation_id, user)
    elif subscription_id is not None:
        advance_result = await subscription_service.advance_for_manual_entry(session, subscription_id, user, date)
    elif installment_id is not None:
        advance_result = await installment_service.advance_for_manual_entry(session, installment_id, user, date)
    # Retire the expenses first-run sample once the user has their first expense.
    await settings_service.retire_sample(session, user.id, "expenses")
    await session.commit()
    return entry, advance_result


# Pre-pays N obligation cycles atomically in one Mark Paid click (Phase 3, follow-up Item 2).
# Inserts `cycles` expense rows all dated `date` and advances next_due_date `cycles` times
# before a single session.commit() — all-or-nothing. Returns (last_entry, advance_result) where
# advance_result spans the full walk: previous_cursor is the obligation's cursor BEFORE the
# loop, new_cursor is where it ended after the final advance. The session's framework-level
# context manager (db.py:get_session) rolls back on any raised exception, so the function
# doesn't need its own try/except — any in-loop raise discards every pending insert + cursor
# mutation. The reconciliation stale mark fires ONCE after the loop (idempotent regardless of
# how many rows landed). Raises:
#   - NotFoundError when the obligation can't be found / isn't owned (router → 404 via global handler)
#   - ValueError when the obligation isn't recurring with a known recurrence pattern, when cycles
#     is outside [1, MAX_CYCLES_PER_MARK_PAID], or when a concurrent transaction deletes the
#     obligation mid-loop (router → 400 via its try/except).
# Sub/installment IDs are forbidden by the schema validator on the multi-cycle path so they're
# not threaded through.
async def create_expenses_for_obligation_cycles(
    session: AsyncSession,
    user: User,
    *,
    cycles: int,
    date: date_type,
    amount: Decimal,
    currency: str,
    payment_obligation_id: int,
    category: ExpenseCategory | None = None,
    notes: str | None = None,
    payment_method: str | None = None,
    credit_card_id: int | None = None,
    source: str = "manual",
) -> tuple[ExpenseEntry, AdvanceResult]:
    # Defensive cycles bound. The schema enforces 1..MAX_CYCLES_PER_MARK_PAID on the HTTP
    # path; this guard catches internal callers and survives `python -O` (`assert` would not).
    if cycles < 1 or cycles > MAX_CYCLES_PER_MARK_PAID:
        raise ValueError(f"cycles must be in [1, {MAX_CYCLES_PER_MARK_PAID}].")

    # SEC-4: get_obligation below validates the obligation FK, but the card FK has no other
    # owner check before its post-loop stale-mark, so validate it here.
    await _validate_owned_fks(session, user, credit_card_id=credit_card_id)
    obligation = await payment_obligation_service.get_obligation(session, payment_obligation_id, user)
    # Recurrence must be a known cycle value — None is one-off, any string not in
    # OBLIGATION_MONTH_STEP would otherwise pass the `is None` check but produce N
    # rows with a frozen cursor (compute_obligation_advance returns the date unchanged
    # for unrecognised recurrence values).
    if obligation.recurrence is None or obligation.recurrence not in OBLIGATION_MONTH_STEP:
        raise ValueError("Multi-cycle Mark Paid requires a recurring obligation with a known recurrence pattern.")

    first_previous_cursor: str | None = None
    last_entry: ExpenseEntry | None = None
    last_advance: AdvanceResult | None = None
    for _ in range(cycles):
        last_entry = await _insert_expense_row(
            session,
            user,
            date=date,
            amount=amount,
            currency=currency,
            category=category,
            notes=notes,
            payment_method=payment_method,
            credit_card_id=credit_card_id,
            source=source,
            payment_obligation_id=payment_obligation_id,
        )
        advance = await payment_obligation_service.advance_or_archive(session, payment_obligation_id, user)
        # advance_or_archive returns None only when the obligation can't be found —
        # a concurrent delete between the initial get_obligation and this lookup. Surface
        # explicitly rather than silently dropping the cursor change from the response
        # toast (which would also leave dangling FK rows in the partial batch).
        if advance is None:
            raise ValueError("Linked obligation disappeared mid-loop.")
        last_advance = advance
        if first_previous_cursor is None:
            first_previous_cursor = advance.previous_cursor

    # Stale-mark fires once for the whole batch (idempotent + every row shares card+currency+date).
    if credit_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, credit_card_id, currency, date)

    # Coalesce so the toast reads "before loop -> after N advances" instead of "step N-1 -> step N".
    # last_entry / last_advance / first_previous_cursor are all guaranteed non-None at this point
    # because cycles >= 1 and the loop body raises rather than yielding None.
    assert last_entry is not None and last_advance is not None and first_previous_cursor is not None
    coalesced = replace(last_advance, previous_cursor=first_previous_cursor)
    # Retire the expenses first-run sample once the user has their first expense.
    await settings_service.retire_sample(session, user.id, "expenses")
    await session.commit()
    return last_entry, coalesced


# Update an existing expense entry. Only provided fields are changed.
# Marks stale on both the prior and the new (card, currency, date) when either has credit_card_id.
# Commitment FK transitions trigger the symmetric advance / reverse model (Phase 3, follow-up
# Items 10 + symmetric edit, audit round 2). For each FK type independently:
#   - X -> None (clear)          : reverse OLD plan if this expense was its most-recent linked.
#   - None -> Y (add)            : advance NEW plan (subject to Item 9's matched-equals-current rule).
#   - X -> Y (swap, same type)   : reverse OLD plan + advance NEW plan.
#   - cross-type swap            : reverse OLD plan + advance NEW plan (different plan types).
#   - unchanged                  : no-op.
# Mutual exclusivity at the row level (at most one OLD FK set) + the Pydantic validator
# (at most one NEW FK set) means at most one reverse target and at most one advance target
# fire per update — so the response carries at most one of each. Returns
# (entry, advance_result, reverse_result) so the router can populate the response's
# advance_change + reverse_change fields for the frontend toast.
async def update_expense(
    session: AsyncSession,
    expense_id: int,
    user: User,
    **fields: object,
) -> tuple[ExpenseEntry, AdvanceResult | None, ReverseResult | None]:
    entry = await get_expense(session, expense_id, user)
    old_card_id = entry.credit_card_id
    old_currency = entry.currency
    old_date = entry.date
    old_obligation_id = entry.payment_obligation_id
    old_subscription_id = entry.subscription_id
    old_installment_id = entry.installment_id

    # New FK values: if the client set the field, take their value; otherwise hold the
    # prior value (no change). Preserves the JSON Merge Patch convention (omitted = unchanged).
    new_obligation_id = fields["payment_obligation_id"] if "payment_obligation_id" in fields else old_obligation_id
    new_subscription_id = fields["subscription_id"] if "subscription_id" in fields else old_subscription_id
    new_installment_id = fields["installment_id"] if "installment_id" in fields else old_installment_id
    new_card_id = fields["credit_card_id"] if "credit_card_id" in fields else old_card_id

    # Effective payment pairing after the merge: a kept-or-set card id requires the
    # effective method to be credit_card (the schema validator only sees same-request pairs).
    new_payment_method = fields["payment_method"] if "payment_method" in fields else entry.payment_method
    if new_card_id is not None and new_payment_method != PaymentMethod.credit_card:
        raise PaymentPairingError()

    # Reverse target: OLD plan that loses this expense. At most one fires (mutual exclusivity
    # on the row guarantees at most one old FK is set). Resolve most-recent BEFORE mutation
    # so the check sees the row still linked.
    reverse_target: tuple[str, int] | None = None
    if old_obligation_id is not None and new_obligation_id != old_obligation_id:
        if await expense_repository.is_most_recent_linked_obligation_expense(session, user.id, old_obligation_id, entry.id):
            reverse_target = ("obligation", old_obligation_id)
    elif old_subscription_id is not None and new_subscription_id != old_subscription_id:
        if await expense_repository.is_most_recent_linked_subscription_expense(session, user.id, old_subscription_id, entry.id):
            reverse_target = ("subscription", old_subscription_id)
    elif old_installment_id is not None and new_installment_id != old_installment_id:
        if await expense_repository.is_most_recent_linked_installment_expense(session, user.id, old_installment_id, entry.id):
            reverse_target = ("installment", old_installment_id)

    # Advance target: NEW plan that gains this expense. At most one fires (Pydantic validator
    # caps NEW FKs at one set value). Fires on add (None -> Y) and on swap (X -> Y where Y
    # differs from X across same or different FK types).
    advance_target: tuple[str, int] | None = None
    if new_obligation_id is not None and new_obligation_id != old_obligation_id:
        advance_target = ("obligation", new_obligation_id)
    elif new_subscription_id is not None and new_subscription_id != old_subscription_id:
        advance_target = ("subscription", new_subscription_id)
    elif new_installment_id is not None and new_installment_id != old_installment_id:
        advance_target = ("installment", new_installment_id)

    # SEC-4: validate any newly-set or changed FK belongs to the user before mutating the row or
    # stale-marking a card. Unchanged FKs were already validated when first attached.
    await _validate_owned_fks(
        session,
        user,
        credit_card_id=new_card_id if new_card_id != old_card_id else None,
        payment_obligation_id=new_obligation_id if new_obligation_id != old_obligation_id else None,
        subscription_id=new_subscription_id if new_subscription_id != old_subscription_id else None,
        installment_id=new_installment_id if new_installment_id != old_installment_id else None,
    )

    for key, value in fields.items():
        setattr(entry, key, value)
    await expense_repository.save(session, entry)

    if old_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, old_card_id, old_currency, old_date)
    moved = entry.credit_card_id != old_card_id or entry.currency != old_currency or entry.date != old_date
    if entry.credit_card_id is not None and moved:
        await card_reconciliation_service.mark_stale_for_date(session, entry.credit_card_id, entry.currency, entry.date)

    reverse_result: ReverseResult | None = None
    if reverse_target is not None:
        plan_type, plan_id = reverse_target
        if plan_type == "obligation":
            reverse_result = await payment_obligation_service.reverse_for_unlink(session, plan_id, user)
        elif plan_type == "subscription":
            # Pass the row's pre-edit date: the reverse fires only if that link's advance
            # decision (recomputed) actually moved the cursor.
            reverse_result = await subscription_service.reverse_for_unlink(session, plan_id, user, old_date)
        elif plan_type == "installment":
            reverse_result = await installment_service.reverse_for_unlink(session, plan_id, user, old_date)

    advance_result: AdvanceResult | None = None
    if advance_target is not None:
        plan_type, plan_id = advance_target
        if plan_type == "obligation":
            advance_result = await payment_obligation_service.advance_or_archive(session, plan_id, user)
        elif plan_type == "subscription":
            advance_result = await subscription_service.advance_for_manual_entry(session, plan_id, user, entry.date)
        elif plan_type == "installment":
            advance_result = await installment_service.advance_for_manual_entry(session, plan_id, user, entry.date)

    await session.commit()
    await session.refresh(entry)
    return entry, advance_result, reverse_result


# Delete an expense entry. Marks any reconciliation covering the entry's date stale.
# When the deleted row had a commitment FK AND was the most-recent linked expense for that FK,
# the plan's cursor walks back one step (Phase 3, follow-up Item 10). Returns the reverse_result
# so the router can include the cursor delta in the response body for Item 7's toast.
async def delete_expense(session: AsyncSession, expense_id: int, user: User) -> ReverseResult | None:
    entry = await get_expense(session, expense_id, user)
    old_card_id = entry.credit_card_id
    old_currency = entry.currency
    old_date = entry.date
    old_obligation_id = entry.payment_obligation_id
    old_subscription_id = entry.subscription_id
    old_installment_id = entry.installment_id

    # Resolve most-recent-linked BEFORE delete — once the row is gone, the check would see
    # the next-newest row as "most recent" and reverse wouldn't fire when it should.
    reverse_target: tuple[str, int] | None = None
    if old_obligation_id is not None:
        if await expense_repository.is_most_recent_linked_obligation_expense(session, user.id, old_obligation_id, entry.id):
            reverse_target = ("obligation", old_obligation_id)
    elif old_subscription_id is not None:
        if await expense_repository.is_most_recent_linked_subscription_expense(session, user.id, old_subscription_id, entry.id):
            reverse_target = ("subscription", old_subscription_id)
    elif old_installment_id is not None:
        if await expense_repository.is_most_recent_linked_installment_expense(session, user.id, old_installment_id, entry.id):
            reverse_target = ("installment", old_installment_id)

    await expense_repository.delete(session, entry)
    if old_card_id is not None:
        await card_reconciliation_service.mark_stale_for_date(session, old_card_id, old_currency, old_date)

    reverse_result: ReverseResult | None = None
    if reverse_target is not None:
        plan_type, plan_id = reverse_target
        if plan_type == "obligation":
            reverse_result = await payment_obligation_service.reverse_for_unlink(session, plan_id, user)
        elif plan_type == "subscription":
            reverse_result = await subscription_service.reverse_for_unlink(session, plan_id, user, old_date)
        elif plan_type == "installment":
            reverse_result = await installment_service.reverse_for_unlink(session, plan_id, user, old_date)

    await session.commit()
    return reverse_result


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


# Returns the preview decision for a manual entry's effect on the linked plan's cursor
# (Phase 3, follow-up 3b). The frontend calls this from the expense form to decide whether
# to show the soft-confirm dialog before save. Exactly one of subscription_id / installment_id
# must be provided; raises NotFoundError when the referenced plan doesn't belong to the user.
# The "neither set" branch is defensive — the router enforces mutual exclusivity with 400 —
# and is unreachable in practice via the HTTP path.
async def find_cycle_advance_decision(
    session: AsyncSession,
    user: User,
    *,
    subscription_id: int | None = None,
    installment_id: int | None = None,
    entry_date: date_type,
) -> CycleAdvanceDecision:
    if subscription_id is not None:
        sub = await subscription_repository.get_by_id(session, subscription_id, user.id)
        if sub is None:
            raise NotFoundError("Subscription not found.")
        return subscription_service.compute_subscription_advance_for_manual_entry(sub, entry_date)
    if installment_id is not None:
        inst = await installment_repository.get_by_id(session, installment_id, user.id)
        if inst is None:
            raise NotFoundError("Installment not found.")
        return installment_service.compute_installment_advance_for_manual_entry(inst, entry_date)
    raise NotFoundError("Either subscription_id or installment_id is required.")
