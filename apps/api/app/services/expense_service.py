from dataclasses import dataclass
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import AdvanceResult, CycleAdvanceDecision, NotFoundError, ReverseResult
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.user import User
from app.repositories import expense_repository, installment_repository, subscription_repository
from app.services import (
    card_reconciliation_service,
    installment_service,
    payment_obligation_service,
    subscription_service,
)

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
    advance_result: AdvanceResult | None = None
    if payment_obligation_id is not None:
        advance_result = await payment_obligation_service.advance_or_archive(session, payment_obligation_id, user)
    elif subscription_id is not None:
        advance_result = await subscription_service.advance_for_manual_entry(session, subscription_id, user, date)
    elif installment_id is not None:
        advance_result = await installment_service.advance_for_manual_entry(session, installment_id, user, date)
    await session.commit()
    return entry, advance_result


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
            reverse_result = await subscription_service.reverse_for_unlink(session, plan_id, user)
        elif plan_type == "installment":
            reverse_result = await installment_service.reverse_for_unlink(session, plan_id, user)

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
            reverse_result = await subscription_service.reverse_for_unlink(session, plan_id, user)
        elif plan_type == "installment":
            reverse_result = await installment_service.reverse_for_unlink(session, plan_id, user)

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
