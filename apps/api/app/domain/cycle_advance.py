from dataclasses import dataclass
from datetime import date as date_type


# Result of a manual-entry advance decision (Phase 3, follow-up 3b). Shared by
# subscription_service and installment_service: the preview endpoint and the actual
# write path both compute this so the soft-confirm dialog and the eventual save
# can't disagree. `next_expected_date` is the closest cycle the entry was matched
# against (informational when `would_advance` is False).
@dataclass(frozen=True)
class CycleAdvanceDecision:
    would_advance: bool
    distance_days: int
    next_expected_date: date_type
