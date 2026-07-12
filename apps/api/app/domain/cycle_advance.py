from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as date_type
from typing import Literal

from app.utils.dates import add_months, advance_by_cycle, step_back_by_cycle

PlanType = Literal["obligation", "subscription", "installment"]


# Result of a manual-entry advance decision (Phase 3, follow-up 3b). Shared by
# subscription_service and installment_service: the preview endpoint and the actual
# write path both compute this so the soft-confirm dialog and the eventual save
# can't disagree. `next_expected_date` is the closest cycle the entry was matched
# against (informational when `would_advance` is False). `multi_jump` is True when
# the matched cycle sits AHEAD of the current cursor by more than one step (pre-pay
# or mis-click); per follow-up Item 9 (Option C) these cases save the link but do NOT
# advance — the scheduler's back-fill loop + partial UNIQUE INDEX dedup handle catch-up.
@dataclass(frozen=True)
class CycleAdvanceDecision:
    would_advance: bool
    distance_days: int
    next_expected_date: date_type
    multi_jump: bool = False


# Outcome of an actual advance that landed (Phase 3, follow-up Item 7). Returned by
# the three service-level advance entry points (`payment_obligation_service.advance_or_archive`,
# `subscription_service.advance_for_manual_entry`, `installment_service.advance_for_manual_entry`)
# so the expense create response can carry enough information for the frontend toast.
# `previous_cursor` / `new_cursor` are stringified for uniformity across plan types — the
# frontend formats per `plan_type`. `new_cursor` is empty when the plan archived (one-off
# obligation Marked Paid, installment past its final step). `total_count` is populated for
# installments (the plan's `installments_count`) so the toast can read "2 of 12
# installments paid" without a client-side lookup against a potentially-stale
# active-plans list.
@dataclass(frozen=True)
class AdvanceResult:
    plan_type: PlanType
    plan_id: int
    plan_name: str
    previous_cursor: str
    new_cursor: str
    total_count: int | None = None


# Outcome of a reverse-cursor walk after the most-recent linked expense was deleted
# or unlinked (Phase 3, follow-up Item 10). Symmetric to AdvanceResult — the response
# schema exposes it on PUT / DELETE so Item 7's toast composes the reverse copy. When
# a one-off obligation or fully-paid installment re-activates as part of the reverse,
# `previous_cursor` reads as an empty string (the archive sentinel) so the frontend
# can distinguish from a same-date reverse on the active path. `total_count` mirrors
# AdvanceResult — populated for installments only.
@dataclass(frozen=True)
class ReverseResult:
    plan_type: PlanType
    plan_id: int
    plan_name: str
    previous_cursor: str
    new_cursor: str
    total_count: int | None = None


# Returns the subscription cycle date closest to `target_date` measured by absolute
# day distance (Phase 3, follow-up 3b). Walks the cycle anchored on next_billing_date
# forward or backward — including PAST cycles before the current cursor — and picks
# the candidate with the smallest |target - cycle|. Pure function; the caller checks
# whether the matched cycle equals the current cursor before advancing (Item 9, Option C).
# The closest-cycle math implicitly enforces a half-cycle window around the cursor — an
# entry within half a cycle of the cursor matches it; further out, it matches a neighbour
# and the strict-equality predicate refuses to advance. Defensive safety cap on the walk
# prevents runaway loops on degenerate cycles.
def closest_subscription_cycle(
    next_billing_date: date_type,
    billing_cycle: str,
    target_date: date_type,
    *,
    anchor_day: int | None = None,
) -> date_type:
    if anchor_day is None:
        anchor_day = next_billing_date.day
    # Forward walk first if the target is at-or-after the cursor.
    if target_date >= next_billing_date:
        cursor = next_billing_date
        steps = 0
        while steps < 1000:
            nxt = advance_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
            if nxt <= cursor or nxt > target_date:
                break
            cursor = nxt
            steps += 1
        nxt = advance_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
        if nxt <= cursor:
            return cursor
        return cursor if abs((cursor - target_date).days) <= abs((nxt - target_date).days) else nxt
    # Backward walk: the target is before the current cursor.
    cursor = next_billing_date
    steps = 0
    while steps < 1000:
        prev = step_back_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
        if prev >= cursor or prev < target_date:
            break
        cursor = prev
        steps += 1
    prev = step_back_by_cycle(cursor, billing_cycle, anchor_day=anchor_day)
    if prev >= cursor:
        return cursor
    return cursor if abs((cursor - target_date).days) <= abs((prev - target_date).days) else prev


# Returns the (index, date) of the installment closest to `target_date` for an installment
# plan, or None when the plan is already fully paid (`current_installment > installments_count`).
# Indices are 1-based; date = add_months(start_date, idx - 1). Pure function; the caller
# checks whether the matched installment equals the current cursor before advancing
# (Item 9, Option C). The closest-installment math implicitly enforces a half-month
# window around the cursor.
def closest_installment_cuota(
    start_date: date_type,
    current_installment: int,
    installments_count: int,
    target_date: date_type,
) -> tuple[int, date_type] | None:
    if current_installment > installments_count:
        return None
    # Closed-form approximation: compare target's month offset from start_date to the
    # installment grid, then check the 1-step neighbourhood to absorb the short-month clamp.
    months_diff = (target_date.year - start_date.year) * 12 + (target_date.month - start_date.month)
    approx_idx = months_diff + 1
    candidates: list[tuple[int, date_type]] = []
    for idx in (approx_idx - 1, approx_idx, approx_idx + 1):
        clamped = max(1, min(idx, installments_count))
        cuota_date = add_months(start_date, clamped - 1)
        candidates.append((clamped, cuota_date))
    best = min(candidates, key=lambda pair: abs((pair[1] - target_date).days))
    return best


# Core shared claim rule: binds each linked-expense date to the subscription cycle it
# matches under the same closest-cycle rule advance_for_manual_entry uses (implicit
# half-cycle window). Returns the set of cycle dates claimed by at least one expense.
# Used by the scheduler back-fill dedup (skip claimed cycles) and mirrored per-expense
# by the calendar's paid walker.
def claimed_subscription_cycles(
    next_billing_date: date_type,
    billing_cycle: str,
    expense_dates: Iterable[date_type],
    *,
    anchor_day: int | None = None,
) -> set[date_type]:
    return {closest_subscription_cycle(next_billing_date, billing_cycle, d, anchor_day=anchor_day) for d in expense_dates}


# Installment counterpart: returns the set of claimed 1-based cuota indices. Passes
# current_installment=1 to the matcher so the full grid is scanned (the fully-paid None
# guard is about advancing, not about re-deriving claims).
def claimed_installment_cuotas(
    start_date: date_type,
    installments_count: int,
    expense_dates: Iterable[date_type],
) -> set[int]:
    claimed: set[int] = set()
    for d in expense_dates:
        match = closest_installment_cuota(start_date, 1, installments_count, d)
        if match is not None:
            claimed.add(match[0])
    return claimed


# True when a linked expense dated entry_date is the one whose advance moved the
# subscription's cursor to next_billing_date: re-running the create path's closest-cycle
# match must bind the expense to the cycle immediately BEFORE the current cursor (the
# pre-advance position). Historical back-links and multi-jump pre-pays bind elsewhere,
# so deleting them must not walk the cursor back.
def subscription_link_advanced_cursor(
    next_billing_date: date_type,
    billing_cycle: str,
    entry_date: date_type,
    *,
    anchor_day: int | None = None,
) -> bool:
    prev_cycle = step_back_by_cycle(next_billing_date, billing_cycle, anchor_day=anchor_day)
    if prev_cycle >= next_billing_date:
        return False
    closest = closest_subscription_cycle(next_billing_date, billing_cycle, entry_date, anchor_day=anchor_day)
    return closest == prev_cycle


# Installment counterpart: the link advanced the cursor iff it binds to the cuota
# immediately before the current one (current_installment - 1). Also covers the
# fully-paid state (current = count + 1 binds against cuota `count`).
def installment_link_advanced_cursor(
    start_date: date_type,
    current_installment: int,
    installments_count: int,
    entry_date: date_type,
) -> bool:
    if current_installment <= 1:
        return False
    match = closest_installment_cuota(start_date, 1, installments_count, entry_date)
    return match is not None and match[0] == current_installment - 1
