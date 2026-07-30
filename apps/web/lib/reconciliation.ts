/*
 * True for an expense / income row that a reconciliation created — the adjustment posted by the card
 * or the account reconciliation flow. Such a row is derived, not authored: its amount IS the
 * reconciliation's recorded `difference`, so mutating it directly makes the reconciliation lie.
 *
 * Both the Edit and the Delete affordance are withheld, because the API refuses both with
 * 409 `reconciliation_owned_entry`. Delete is not an escape hatch: the reverse pointer
 * (`card_reconciliations/account_reconciliations.adjustment_*_id`) is ON DELETE SET NULL, so removing
 * the entry leaves the reconciliation alive with a null pointer and a `difference` it no longer
 * applies, while the balance silently snaps back.
 *
 * The supported way to change one is to re-run or delete its RECONCILIATION, which recomputes or
 * cascade-drops the adjustment (`expense_entries/income_entries.{reconciliation_id,
 * account_reconciliation_id}` are ON DELETE CASCADE).
 *
 * Keyed on the foreign keys, not on `source === 'reconciliation'`, so this predicate agrees exactly
 * with the backend guard. `source` records provenance and survives a restore, which nulls both links —
 * a restored adjustment is a plain historical entry that nothing owns, so it stays mutable. What such
 * a row still cannot do is round-trip the entry form, and that is a separate concern owned by
 * isSystemExpenseCategory / isSystemIncomeCategory in lib/utils/categories.
 */
export function isReconciliationOwned(entry: {
  reconciliationId: number | null;
  accountReconciliationId: number | null;
}): boolean {
  return entry.reconciliationId !== null || entry.accountReconciliationId !== null;
}
