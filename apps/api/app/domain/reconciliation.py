# Reconciliation ownership rule shared by the expense and income services. Both reconciliation
# features — card (Phase 3, Step 5) and account (the cash/bank money engine) — post their difference
# as an ordinary expense_entries / income_entries row linked back to the reconciliation that created
# it. This module owns the one rule that keeps such a row honest.

from app.domain.errors import ReconciliationOwnedEntryError


# Raises ReconciliationOwnedEntryError when either reconciliation link is set, i.e. the row is a
# reconciliation's adjustment rather than an entry the user authored. Called by the expense / income
# services on update and delete, before any mutation or side-effect lookup, so a rejected request
# writes nothing. Both links are checked because the two features use separate columns:
# reconciliation_id (card) and account_reconciliation_id (account); a row carries at most one.
#
# Keyed on the foreign keys rather than source == 'reconciliation' deliberately. `source` records
# provenance and survives a restore, which nulls both links — a restored adjustment is a plain
# historical entry that nothing owns, so it must stay mutable. Other flows (scheduler, importers,
# shortcut) also write `source`, so it is the wrong fact to gate on.
def ensure_not_reconciliation_owned(reconciliation_id: int | None, account_reconciliation_id: int | None) -> None:
    if reconciliation_id is not None or account_reconciliation_id is not None:
        raise ReconciliationOwnedEntryError()
