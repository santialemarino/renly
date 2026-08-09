# Card reconciliation business logic (Phase 3, Step 5 — Option F).
# Implements:
#   - compute_bucket_balance_at(): running-balance snapshot at a date (shared with Payments Calendar).
#   - create_or_replace(): atomic delete-old + insert-new for a (card, currency, period) reconciliation,
#     including the matching signed adjustment expense.
#   - mark_stale_for_date(): stale-detection hook called from expense/settlement create/update/delete.
#   - list_recent_statements(): drives the Reconciliations sub-section UI per bucket.

from datetime import date as date_type
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import CardReconciliationFuturePeriodError, NotFoundError, ReconciliationPeriodMismatchError
from app.models.card_reconciliation import CardReconciliation
from app.models.credit_card import CreditCard
from app.models.expense_entry import ExpenseCategory, ExpenseEntry
from app.models.user import User
from app.repositories import (
    card_reconciliation_repository,
    credit_card_repository,
    expense_repository,
)
from app.services import settings_service
from app.utils.dates import compute_statement_period, resolve_day_in_month

# Number of recent statement periods to surface per bucket in the Reconciliations sub-section.
RECENT_STATEMENTS_LIMIT = 12


# --- Pure helpers ---


# Pure computation: bucket-currency adjustment from the bank's statement balance and the app's computed
# running balance. Positive => the bank charged more than Renly knew (fees / taxes / FX); negative => a
# credit or refund posted to the card; zero => no adjustment. Both non-zero cases become one signed
# card-linked expense, because a bucket balance only moves on expenses and settlements.
def compute_reconciliation_difference(statement_balance: Decimal, computed_balance: Decimal) -> Decimal:
    return statement_balance - computed_balance


# Running balance (expenses − settlements) at each closing date, from per-day sums. `closings`
# must be ascending; the daily lists are date-ascending. Two-pointer cumulative walk — the
# arithmetic matches compute_bucket_balance_at exactly (sum of ALL rows dated <= closing, from the
# beginning of the bucket's history).
def cumulative_balances_at(
    closings: list[date_type],
    expense_daily: list[tuple[date_type, Decimal]],
    settlement_daily: list[tuple[date_type, Decimal]],
) -> dict[date_type, Decimal]:
    balances: dict[date_type, Decimal] = {}
    running = Decimal(0)
    ei = si = 0
    for closing in closings:
        while ei < len(expense_daily) and expense_daily[ei][0] <= closing:
            running += expense_daily[ei][1]
            ei += 1
        while si < len(settlement_daily) and settlement_daily[si][0] <= closing:
            running -= settlement_daily[si][1]
            si += 1
        balances[closing] = running
    return balances


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


# Batched variant of compute_bucket_balance_at: running-balance snapshots for every (card, currency)
# bucket with activity across `card_ids`, all evaluated at the same as_of_date — two grouped queries
# total. Returns {(card_id, currency): balance}; buckets absent from both maps have balance 0 and
# are omitted.
async def compute_bucket_balances_at(
    session: AsyncSession,
    card_ids: list[int],
    as_of_date: date_type,
) -> dict[tuple[int, str], Decimal]:
    expenses = await card_reconciliation_repository.sum_expenses_by_bucket_at(session, card_ids, as_of_date)
    settlements = await card_reconciliation_repository.sum_settlements_by_bucket_at(session, card_ids, as_of_date)
    return {key: expenses.get(key, Decimal(0)) - settlements.get(key, Decimal(0)) for key in expenses.keys() | settlements.keys()}


# Builds the last RECENT_STATEMENTS_LIMIT statement periods for a card+currency, newest first.
# Each entry carries period bounds, the running-balance snapshot at period_end (recomputed live),
# and the reconciliation row for that period if one exists.
async def list_recent_statements(
    session: AsyncSession,
    card: CreditCard,
    currency: str,
) -> list[dict]:
    today = await settings_service.get_user_today(session, card.user_id)

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

    # Batch the running balances: two grouped queries (per-day expense/settlement sums up to the
    # newest closing), then a cumulative walk in Python — replaces up to 2 SUM round-trips per
    # statement. Daily grouping (not monthly) because statement periods close mid-month on the
    # card's closing_day, so calendar-month buckets would not align with period_end.
    expense_daily = await card_reconciliation_repository.list_expense_daily_sums(session, card.id, currency, latest_close)
    settlement_daily = await card_reconciliation_repository.list_settlement_daily_sums(session, card.id, currency, latest_close)
    balance_at_closing = cumulative_balances_at(sorted(closings), expense_daily, settlement_daily)

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
        computed = balance_at_closing[closing]
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
#   2. Mark every LATER period stale, because both the adjustment just dropped and the one about to be
#      written are dated period_end and so sit inside every later period's balance.
#   3. Compute the running-balance snapshot at period_end.
#   4. Compute the difference; create the matching signed adjustment expense (dated on period_end,
#      tagged source='reconciliation', linked via reconciliation_id) when difference != 0.
#   5. Write the reconciliation row and patch its back-pointer to the adjustment id.
#
# Unlike account reconciliation, an out-of-order (older) period is ALLOWED here rather than rejected.
# The account version has no repair path — reconciliations there simply append, so an older one can
# only be undone by deleting every later one first, which is why it is forward-only. This one replaces:
# re-running a period drops its old row and adjustment and recomputes from scratch, so re-running the
# affected periods in ascending order always converges. Refusing would import a workaround for a
# limitation cards do not have, and would have to withhold Reconcile on nearly every row of a surface
# whose whole shape is a list of individually reconcilable statements. Staleness is the signal instead.
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
    # The period must be one this card actually issues. Without this an arbitrary window is accepted,
    # and the row it writes is unreachable afterwards: list_recent_statements only matches a
    # reconciliation by the (period_start, period_end) pair compute_statement_period derives from the
    # closing day, so the row never renders and its adjustment — a real, balance-moving expense — can
    # be deleted from neither the statements table (no row) nor the expenses table (409, it is
    # reconciliation-owned). Checking period_end alone is enough: the start is derived from it.
    if compute_statement_period(card.closing_day, period_end) != (period_start, period_end):
        raise ReconciliationPeriodMismatchError("The period does not match a statement period for this card.")
    today = await settings_service.get_user_today(session, user.id)
    if period_end > today:
        raise CardReconciliationFuturePeriodError()

    # Drop the prior row (and its adjustment via the CASCADE on expense_entries.reconciliation_id /
    # income_entries.reconciliation_id) before inserting a fresh pair. session.delete + flush triggers
    # the cascade synchronously within this transaction so the UNIQUE constraint check on the new
    # insert below sees a clean slot.
    prior = await card_reconciliation_repository.get_by_period(session, card_id, currency, period_start, period_end)
    prior_had_adjustment = prior is not None and prior.adjustment_expense_id is not None
    if prior is not None:
        await card_reconciliation_repository.delete(session, prior)
        await session.flush()

    computed = await compute_bucket_balance_at(session, card_id, currency, period_end)
    difference = compute_reconciliation_difference(statement_balance, computed)

    # Propagate only when a dated row actually enters or leaves the ledger — an adjustment is dropped
    # by the replace above, or a new one is written below. A first-time reconciliation that matches to
    # the cent writes nothing, so flagging later periods would claim their figures moved when they did
    # not: the same lie as the missed-flag bug, in the other direction.
    #
    # Ordering is load-bearing: this period's own slot is empty right now (any prior row was deleted
    # and flushed, and the new one is not written yet), so period_end >= period_end matches ONLY
    # strictly later periods. That is what lets the fresh row below be born is_stale=False without
    # threading an exclude-id through the hook.
    if prior_had_adjustment or difference != 0:
        await mark_stale_for_date(session, card_id, currency, period_end)

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

    # One signed, card-linked adjustment in both directions. A bucket balance is
    # `sum(expenses) - sum(settlements)`, so ONLY an expense can move it — an income row would leave
    # the card overstated no matter its amount. A positive difference (the bank charged more than
    # Renly knew) is a fee/tax; a negative one is a credit and carries a negative amount, which the
    # bucket sum subtracts correctly. The credit is NOT account-linked: it cleared card debt, it did
    # not deposit cash. A refund paid to a bank account instead never moves the card statement, so it
    # produces no adjustment here and is recorded as ordinary account-linked income.
    if difference != 0:
        is_credit = difference < 0
        adjustment_expense = ExpenseEntry(
            user_id=user.id,
            date=period_end,
            amount=difference,
            currency=currency,
            category=ExpenseCategory.card_credits_and_refunds if is_credit else ExpenseCategory.card_fees_and_taxes,
            payment_method="credit_card",
            credit_card_id=card_id,
            source="reconciliation",
            reconciliation_id=reconciliation.id,
        )
        adjustment_expense = await expense_repository.create(session, adjustment_expense)
        reconciliation.adjustment_expense_id = adjustment_expense.id
        await card_reconciliation_repository.save(session, reconciliation)

    await session.commit()
    await session.refresh(reconciliation)
    return reconciliation


# Delete a reconciliation (and cascade-drop its adjustment expense). Any later period is marked stale:
# the adjustment leaving is a dated row disappearing from every balance that summed it, so those
# recorded figures no longer describe reality. Deleting a non-latest period is allowed for the same
# reason create_or_replace allows an out-of-order one — re-running converges, so staleness is the
# honest signal rather than a refusal.
async def delete_reconciliation(
    session: AsyncSession,
    card_id: int,
    reconciliation_id: int,
    user: User,
) -> None:
    rec = await get_reconciliation(session, card_id, reconciliation_id, user)
    currency, period_end = rec.currency, rec.period_end
    had_adjustment = rec.adjustment_expense_id is not None
    await card_reconciliation_repository.delete(session, rec)
    # Flush so the row (and its cascaded adjustment) is gone before the hook queries — otherwise the
    # row being deleted would match its own predicate and be marked stale on the way out.
    await session.flush()
    # Only an adjustment leaving changes a later balance. Deleting a reconciliation that matched to
    # the cent removes no dated row, so nothing downstream moved.
    if had_adjustment:
        await mark_stale_for_date(session, card_id, currency, period_end)
    await session.commit()


# --- Stale-detection hook ---


# Mark every reconciliation whose recorded balance depends on rows dated target_date as stale, for
# (card, currency) — i.e. every period ending on or after that date, since a bucket balance sums all
# history up to period_end. Called from the expense / settlement hooks and from this module's own
# create/delete, because a reconciliation's adjustment is itself a dated expense that moves every
# later period's balance. Callers gate on whether a balance actually moved — flagging on an edit that
# changed nothing would be the same lie as missing one, in the other direction.
#
# The lookup is a range scan over one bucket's reconciliations from target_date forward (bounded by
# idx_card_reconciliations_period_end), not the single row the period-contains predicate returned.
# Already-stale rows are filtered before the UPDATE so a repeated edit writes nothing. Kept as
# read-then-update rather than one conditional UPDATE so the filter stays unit-testable against a
# mocked repository; the row count is a user's reconciled statements for one card, and both
# statements run inside the caller's transaction. Does NOT commit — the caller owns the boundary.
async def mark_stale_for_date(
    session: AsyncSession,
    card_id: int,
    currency: str,
    target_date: date_type,
) -> None:
    affected = await card_reconciliation_repository.list_affected_by_date(session, card_id, currency, target_date)
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
