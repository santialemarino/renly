// Tolerance window (in days) for the manual-dupe expense warning (Phase 3, Step D).
// When the user is entering a manual credit-card expense, the form looks up
// auto-generated expenses (subscription / installment scheduler output) within
// ±DUPE_MATCH_WINDOW_DAYS that match on card / currency / exact amount and shows
// a soft confirmation dialog. Backend mirrors this value in expense_service.py.
export const DUPE_MATCH_WINDOW_DAYS = 15;
