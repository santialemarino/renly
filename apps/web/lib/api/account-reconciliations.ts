// Server-only types + mappers for account reconciliations (Bucket 3 #1).
// Client components fetch via server actions in `account-actions.ts` instead.

import 'server-only';

// --- Raw types (API JSON shape, snake_case) ---

interface AccountReconciliationRaw {
  id: number;
  account_id: number;
  as_of_date: string;
  statement_balance: string;
  computed_balance: string;
  difference: string;
  adjustment_expense_id: number | null;
  adjustment_income_id: number | null;
  reconciled_at: string;
  created_at: string;
  updated_at: string;
}

// --- Frontend types (camelCase) ---

export interface AccountReconciliation {
  id: number;
  accountId: number;
  asOfDate: string;
  statementBalance: string;
  computedBalance: string;
  difference: string;
  adjustmentExpenseId: number | null;
  adjustmentIncomeId: number | null;
  reconciledAt: string;
  createdAt: string;
  updatedAt: string;
}

// --- Mappers ---

export function mapAccountReconciliation(raw: AccountReconciliationRaw): AccountReconciliation {
  return {
    id: raw.id,
    accountId: raw.account_id,
    asOfDate: raw.as_of_date,
    statementBalance: raw.statement_balance,
    computedBalance: raw.computed_balance,
    difference: raw.difference,
    adjustmentExpenseId: raw.adjustment_expense_id,
    adjustmentIncomeId: raw.adjustment_income_id,
    reconciledAt: raw.reconciled_at,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}
