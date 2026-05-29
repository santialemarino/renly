// Error types thrown by `expenses-actions.ts` and consumed by the expense form.
// Lives in its own non-server module because Next.js' "use server" directive forbids
// exporting non-async values (classes, constants) from a server-actions file. Splitting
// the class out keeps the server action file pure-async and lets client components
// import the error type without dragging the actions module into a client bundle.

// 409 from POST/PUT /expenses carries a user-readable `detail` string from the backend's
// IntegrityError handler (Phase 3, follow-up Item 8.2) — typically the partial UNIQUE
// INDEX on (subscription_id, date) / (installment_id, date) catching a duplicate
// scheduler-emitted charge on the same plan+date. We tag the error so the caller can
// surface the backend message verbatim instead of a generic "Failed to save expense".
export class ExpenseConflictError extends Error {
  constructor(public detail: string) {
    super(detail);
    this.name = 'ExpenseConflictError';
  }
}
