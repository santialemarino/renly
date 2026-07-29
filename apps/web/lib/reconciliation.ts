// The `source` value the backend stamps on an adjustment entry created by a card or account
// reconciliation.
export const RECONCILIATION_SOURCE = 'reconciliation';

/*
 * True for an expense / income row that a reconciliation created, which must not be edited directly.
 * Such a row is derived, not authored: its amount IS the reconciliation's recorded `difference`, its
 * category is system-generated and deliberately absent from the pickers, and a card credit carries a
 * NEGATIVE amount that the shared amount input would strip on the first keystroke — saving a
 * sign-flipped value would move the card balance by twice the credit. The API refuses it anyway
 * (`amount > 0`), so the edit affordance could only ever dead-end or corrupt.
 *
 * The supported way to change one is to re-run or delete its reconciliation, which recomputes or
 * cascade-drops the adjustment. Deleting the entry itself stays available — it is the documented
 * escape hatch and the reconciliation's back-pointer clears cleanly.
 */
export function isReconciliationOwned(entry: { source: string }): boolean {
  return entry.source === RECONCILIATION_SOURCE;
}
