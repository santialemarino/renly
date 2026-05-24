# Card reconciliation business logic (Phase 3, Step 5 — Option F).
# Implements:
#   - compute_bucket_balance_at(): running-balance snapshot at a date (shared with Payments Calendar).
#   - create_or_replace(): atomic delete-old + insert-new for a (card, currency, period) reconciliation,
#     including the matching adjustment expense or income.
#   - mark_stale_for_date(): stale-detection hook called from expense/settlement create/update/delete.
#   - list_recent_statements(): drives the Reconciliations sub-section UI per bucket.

from datetime import UTC, datetime
from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import NotFoundError, ReconciliationPeriodMismatchError
from app.models.card_reconciliation import CardReconciliation
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.income_entry import IncomeCategory, IncomeEntry
from app.models.user import User
from app.repositories import (
    card_reconciliation_repository,
    credit_card_repository,
    expense_repository,
    income_repository,
)
from app.utils.dates import compute_statement_period, resolve_day_in_month

# Number of recent statement periods to surface per bucket in the Reconciliations sub-section.
RECENT_STATEMENTS_LIMIT = 12


# --- Pure helpers ---


# Pure computation: bucket-currency adjustment from the bank's statement balance and the app's computed running balance.
# Positive => create an expense (fees / taxes / FX); negative => create an income (credit / refund); zero => no adjustment.
def compute_reconciliation_difference(statement_balance: Decimal, computed_balance: Decimal) -> Decimal:
    return statement_balance - computed_balance


# Running-balance snapshot of a card+currency bucket at as_of_date.
# = sum(expenses dated <= as_of_date) - sum(settlements dated <= as_of_date) for that bucket.
# Used both by reconciliation (computed_balance for the period) and the Payments Calendar card_due event.
async def compute_bucket_balance_at(
    session: AsyncSession,
    card_id: int,
    currency: str,
    as_of_date: date_type,
) -> Decimal:
    expenses = await card_reconciliation_repository.sum_expenses_at(session, card_id, currency, as_of_date)
    settlements = await card_reconciliation_repository.sum_settlements_at(session, card_id, currency, as_of_date)
    return expenses - settlements


# Builds the last RECENT_STATEMENTS_LIMIT statement periods for a card+currency, newest first.
# Each entry carries period bounds, the running-balance snapshot at period_end (recomputed live),
# and the reconciliation row for that period if one exists.
async def list_recent_statements(
    session: AsyncSession,
    card: CreditCard,
    currency: str,
) -> list[dict]:
    today = datetime.now(UTC).date()

    # Find the most recent statement closing date at or before today.
    this_month_close = resolve_day_in_month(card.closing_day, today.year, today.month)
    if this_month_close > today:
        prev_total = today.year * 12 + (today.month - 1) - 1
        prev_y, prev_m = divmod(prev_total, 12)
        prev_m += 1
        latest_close = resolve_day_in_month(card.closing_day, prev_y, prev_m)
    else:
        latest_close = this_month_close

    # Walk backwards one statement at a time, building the candidate closings list.
    closings: list[date_type] = [latest_close]
    cursor = latest_close
    for _ in range(RECENT_STATEMENTS_LIMIT - 1):
        cursor_total = cursor.year * 12 + (cursor.month - 1) - 1
        prev_y, prev_m = divmod(cursor_total, 12)
        prev_m += 1
        cursor = resolve_day_in_month(card.closing_day, prev_y, prev_m)
        closings.append(cursor)

    existing = await card_reconciliation_repository.list_by_card(session, card.id, currency=currency)
    rec_by_period: dict[tuple[date_type, date_type], CardReconciliation] = {(r.period_start, r.period_end): r for r in existing}
    first_activity = await card_reconciliation_repository.get_first_activity_date(session, card.id, currency)

    statements: list[dict] = []
    for closing in closings:
        period_start, period_end = compute_statement_period(card.closing_day, closing)
        rec = rec_by_period.get((period_start, period_end))
        # Visibility rule: keep a statement when it has a reconciliation (explicit record),
        # is the latest closed statement (always reconcilable when a new statement arrives),
        # or sits at-or-after the bucket's first activity (the bucket actually existed by then).
        # Drops pre-history zeros so a fresh card doesn't render 12 rows of "Not reconciled · $0".
        is_latest = closing == latest_close
        post_first_activity = first_activity is not None and period_end >= first_activity
        if rec is None and not is_latest and not post_first_activity:
            continue
        computed = await compute_bucket_balance_at(session, card.id, currency, period_end)
        statements.append(
            {
                "currency": currency,
                "period_start": period_start,
                "period_end": period_end,
                "computed_balance": computed,
                "reconciliation": rec,
            }
        )
    return statements


# --- Reconciliation CRUD ---


# List reconciliations for a card, optionally scoped to a bucket. Ordered by period_end desc.
async def list_reconciliations(
    session: AsyncSession,
    card_id: int,
    user: User,
    *,
    currency: str | None = None,
) -> list[CardReconciliation]:
    await _get_card_or_404(session, card_id, user)
    return await card_reconciliation_repository.list_by_card(session, card_id, currency=currency)


# Get a single reconciliation by id (verifies card ownership).
async def get_reconciliation(
    session: AsyncSession,
    card_id: int,
    reconciliation_id: int,
    user: User,
) -> CardReconciliation:
    await _get_card_or_404(session, card_id, user)
    rec = await card_reconciliation_repository.get_by_id(session, reconciliation_id, card_id)
    if rec is None:
        raise NotFoundError("Reconciliation not found.")
    return rec


# Create-or-replace a reconciliation for (card, currency, period). Atomic:
#   1. If a reconciliation already exists for the period, delete it (cascade drops its adjustment).
#   2. Compute the running-balance snapshot at period_end.
#   3. Compute the difference; create the matching adjustment expense or income (dated on period_end,
#      tagged source='reconciliation', linked via reconciliation_id) when difference != 0.
#   4. Write the reconciliation row and patch its back-pointer to the adjustment id.
# Returns the fresh reconciliation row.
async def create_or_replace(
    session: AsyncSession,
    card_id: int,
    user: User,
    *,
    currency: str,
    period_start: date_type,
    period_end: date_type,
    statement_balance: Decimal,
) -> CardReconciliation:
    card = await _get_card_or_404(session, card_id, user)
    if period_start > period_end:
        raise ReconciliationPeriodMismatchError("period_start must be on or before period_end.")

    # Drop the prior row (and its adjustment via the CASCADE on expense_entries.reconciliation_id /
    # income_entries.reconciliation_id) before inserting a fresh pair. session.delete + flush triggers
    # the cascade synchronously within this transaction so the UNIQUE constraint check on the new
    # insert below sees a clean slot.
    prior = await card_reconciliation_repository.get_by_period(session, card_id, currency, period_start, period_end)
    if prior is not None:
        await card_reconciliation_repository.delete(session, prior)
        await session.flush()

    computed = await compute_bucket_balance_at(session, card_id, currency, period_end)
    difference = compute_reconciliation_difference(statement_balance, computed)

    reconciliation = CardReconciliation(
        user_id=user.id,
        card_id=card_id,
        currency=currency,
        period_start=period_start,
        period_end=period_end,
        statement_balance=statement_balance,
        computed_balance=computed,
        difference=difference,
        is_stale=False,
    )
    reconciliation = await card_reconciliation_repository.create(session, reconciliation)

    if difference > 0:
        adjustment_expense = ExpenseEntry(
            user_id=user.id,
            date=period_end,
            amount=difference,
            currency=currency,
            category=ExpenseCategory.card_fees_and_taxes,
            payment_method="credit_card",
            credit_card_id=card_id,
            source="reconciliation",
            reconciliation_id=reconciliation.id,
        )
        adjustment_expense = await expense_repository.create(session, adjustment_expense)
        reconciliation.adjustment_expense_id = adjustment_expense.id
        await card_reconciliation_repository.save(session, reconciliation)
    elif difference < 0:
        adjustment_income = IncomeEntry(
            user_id=user.id,
            date=period_end,
            amount=-difference,
            currency=currency,
            category=IncomeCategory.card_credits_and_refunds,
            source="reconciliation",
            reconciliation_id=reconciliation.id,
        )
        adjustment_income = await income_repository.create(session, adjustment_income)
        reconciliation.adjustment_income_id = adjustment_income.id
        await card_reconciliation_repository.save(session, reconciliation)

    # Card metadata isn't actually mutated; this line silences the unused-variable lint
    # while keeping ownership verification at the top of the function.
    _ = card

    await session.commit()
    await session.refresh(reconciliation)
    return reconciliation


# Delete a reconciliation (and cascade-drop its adjustment expense or income).
async def delete_reconciliation(
    session: AsyncSession,
    card_id: int,
    reconciliation_id: int,
    user: User,
) -> None:
    rec = await get_reconciliation(session, card_id, reconciliation_id, user)
    await card_reconciliation_repository.delete(session, rec)
    await session.commit()


# --- Stale-detection hook ---


# Mark every reconciliation whose period covers target_date for (card, currency) as stale.
# Called from expense / settlement create / update / delete hooks. No-op when no reconciliation
# is affected, so the cost of the hook on every write is one indexed lookup.
# Does NOT commit — the caller's transaction owns the boundary.
async def mark_stale_for_date(
    session: AsyncSession,
    card_id: int,
    currency: str,
    target_date: date_type,
) -> None:
    affected = await card_reconciliation_repository.list_covering_date(session, card_id, currency, target_date)
    if not affected:
        return
    ids = [r.id for r in affected if r.id is not None and not r.is_stale]
    if not ids:
        return
    await card_reconciliation_repository.mark_stale(session, ids)


# --- Internal ---


# Verifies the card exists and is owned by user. Centralised so every endpoint hits the same 404.
async def _get_card_or_404(session: AsyncSession, card_id: int, user: User) -> CreditCard:
    card = await credit_card_repository.get_by_id(session, card_id, user.id)
    if card is None:
        raise NotFoundError("Credit card not found.")
    return card
