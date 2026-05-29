from dataclasses import dataclass
from datetime import date as date_type
from typing import Literal

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
# obligation Marked Paid, installment past its final cuota). `total_count` is populated for
# installments (the plan's `installments_count`) so the toast can read "cuota 2 of 12"
# without a client-side lookup against a potentially-stale active-plans list.
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
