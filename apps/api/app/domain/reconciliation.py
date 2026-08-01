# Reconciliation rules shared by the expense and income services and their request schemas. Both
# reconciliation features — card (Phase 3, Step 5) and account (the cash/bank money engine) — post
# their difference as an ordinary expense_entries / income_entries row linked back to the
# reconciliation that created it, categorised with a value reserved for true-ups. This module owns the
# two rules that keep such a row honest: only a reconciliation may own one, and only a reconciliation
# may write its category.

from app.domain.errors import ReconciliationOwnedEntryError
from app.models.expense_entry import ExpenseCategory
from app.models.income_entry import IncomeCategory

# Category values only a reconciliation writes — they LABEL a true-up, which is what lets the app
# separate real spending from a balance correction. A user-supplied value here would be a fake
# true-up: indistinguishable in every breakdown from one the app actually computed. Neither picker
# offers them, and the request schemas reject them (see app/schemas/base.py), so they can only ever
# arrive from the reconciliation services, which build their rows through the repositories directly.
SYSTEM_EXPENSE_CATEGORIES: frozenset[ExpenseCategory] = frozenset(
    {
        ExpenseCategory.account_adjustment,
        ExpenseCategory.card_credits_and_refunds,
        ExpenseCategory.card_fees_and_taxes,
    }
)

# The income counterpart. card_credits_and_refunds is legacy — card credits are signed expenses now,
# so nothing writes it — but it stays reserved rather than becoming user-pickable, because historical
# rows carry it and it would otherwise start meaning two different things.
SYSTEM_INCOME_CATEGORIES: frozenset[IncomeCategory] = frozenset(
    {
        IncomeCategory.account_adjustment,
        IncomeCategory.card_credits_and_refunds,
    }
)


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
